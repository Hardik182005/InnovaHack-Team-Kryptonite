"""Extraction pipeline — spec §7.

Layered by cost and certainty:

  CSV/XLSX      -> stdlib csv (pandas used for XLSX when installed)
  digital PDF   -> pdfplumber, then PyMuPDF, then layout-aware line parsing
  scanned PDF   -> Amazon Textract, then Gemini for failed pages only (app/ai)
  SMS / email   -> deterministic regex first

Every row carries its parser, source page/row and extraction confidence so that
§8 can never silently drop a transaction.

Heavy parsers are imported lazily: the deterministic core must stay importable
with no third-party packages installed.
"""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from ..models.enums import Direction
from ..models.transaction import Transaction, money

CALCULATION_VERSION = "extraction.v1"

#: Column aliases from §7, plus common real-world variants.
COLUMN_ALIASES: Dict[str, Sequence[str]] = {
    "date": (
        "transaction date", "posting date", "date", "txn date", "value date",
        "trans date", "book date", "posted",
    ),
    "description": (
        "narration", "particulars", "description", "merchant", "details",
        "transaction details", "remarks", "payee", "name",
    ),
    "debit": ("debit", "withdrawal", "withdrawals", "debit amount", "money out", "paid out"),
    "credit": ("credit", "deposit", "deposits", "credit amount", "money in", "paid in"),
    "amount": ("amount", "transaction amount", "value", "amt"),
    "balance": ("balance", "running balance", "closing balance", "available balance"),
    "reference": ("reference number", "reference", "ref no", "chq/ref no", "cheque no", "utr"),
    "currency": ("currency", "ccy"),
}

DATE_FORMATS = (
    "%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y", "%m-%d-%Y",
    "%d %b %Y", "%d %B %Y", "%b %d, %Y", "%B %d, %Y",
    "%Y/%m/%d", "%d.%m.%Y", "%d-%b-%Y", "%d-%b-%y", "%m/%d/%y", "%d/%m/%y",
)

CURRENCY_SYMBOLS = {"$": "USD", "£": "GBP", "€": "EUR", "₹": "INR", "¥": "JPY"}

_AMOUNT_CLEAN = re.compile(r"[^\d.,\-()]")
_MULTISPACE = re.compile(r"\s{2,}")


@dataclass
class ExtractionResult:
    transactions: List[Transaction] = field(default_factory=list)
    parser: str = ""
    currency: str = "INR"
    warnings: List[str] = field(default_factory=list)
    pages_processed: int = 0
    rows_seen: int = 0
    rows_skipped: List[Tuple[int, str]] = field(default_factory=list)
    calculation_version: str = CALCULATION_VERSION

    @property
    def date_range(self) -> Optional[Tuple[date, date]]:
        if not self.transactions:
            return None
        dates = [t.date for t in self.transactions]
        return min(dates), max(dates)


# ---------------------------------------------------------------------------
# Primitive parsers
# ---------------------------------------------------------------------------


def parse_amount(raw) -> Optional[Decimal]:
    """Parse money from messy statement text.

    Handles `1,234.56`, `(1,234.56)` for negatives, `₹1,234.56`, `1.234,56`
    (European), and trailing `CR`/`DR` markers.
    """
    if raw is None:
        return None
    if isinstance(raw, (int, float, Decimal)):
        try:
            return money(raw)
        except (InvalidOperation, ValueError):
            return None

    s = str(raw).strip()
    if not s:
        return None

    negative = False
    upper = s.upper()
    if upper.endswith("CR"):
        s = s[:-2].strip()
    elif upper.endswith("DR"):
        s = s[:-2].strip()
        negative = True
    if s.startswith("(") and s.endswith(")"):
        negative = True
        s = s[1:-1]
    if s.startswith("-"):
        negative = True

    s = _AMOUNT_CLEAN.sub("", s).replace("(", "").replace(")", "").replace("-", "")
    if not s:
        return None

    # European "1.234,56" — comma is the decimal separator.
    if "," in s and "." in s:
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif "," in s:
        parts = s.split(",")
        if len(parts[-1]) == 2 and len(parts) == 2:
            s = s.replace(",", ".")
        else:
            s = s.replace(",", "")

    try:
        value = money(s)
    except (InvalidOperation, ValueError):
        return None
    return -value if negative else value


def parse_date(raw) -> Optional[date]:
    """Try each known format. Ambiguous d/m vs m/d is resolved by validation."""
    if raw is None:
        return None
    if isinstance(raw, datetime):
        return raw.date()
    if isinstance(raw, date):
        return raw
    s = str(raw).strip()
    if not s:
        return None
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def detect_currency(text: str, default: str = "INR") -> str:
    for symbol, code in CURRENCY_SYMBOLS.items():
        if symbol in text:
            return code
    match = re.search(r"\b(USD|EUR|GBP|INR|JPY|AUD|CAD)\b", text or "", re.I)
    return match.group(1).upper() if match else default


def _map_columns(headers: Sequence[str]) -> Dict[str, int]:
    """Map canonical field -> column index using the §7 alias table."""
    mapping: Dict[str, int] = {}
    normalised = [(h or "").strip().lower() for h in headers]
    for field_name, aliases in COLUMN_ALIASES.items():
        for idx, header in enumerate(normalised):
            if header in aliases:
                mapping[field_name] = idx
                break
        if field_name not in mapping:
            # Substring fallback: "txn date (dd/mm)" still maps to date.
            for idx, header in enumerate(normalised):
                if any(alias in header for alias in aliases):
                    mapping[field_name] = idx
                    break
    return mapping


def _decode(data: bytes) -> str:
    """Encoding detection (§7). chardet when available, else a codec ladder."""
    try:  # pragma: no cover - optional dependency
        import chardet

        guess = chardet.detect(data)
        if guess.get("encoding") and guess.get("confidence", 0) > 0.6:
            return data.decode(guess["encoding"], errors="replace")
    except ImportError:
        pass
    for codec in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            return data.decode(codec)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


# ---------------------------------------------------------------------------
# CSV / XLSX
# ---------------------------------------------------------------------------


def _repair_unbalanced_quotes(text: str) -> Tuple[str, int]:
    """Strip quotes from lines that have an odd number of them.

    An unclosed quote makes Python's csv module treat every following line as a
    continuation of that field, so one malformed row silently swallows the rest
    of the statement. That is a §8 violation — a good transaction after a bad one
    would disappear without a warning.

    Removing the quotes on the offending line confines the damage to that row,
    which is then reported as skipped like any other bad row.
    """
    lines = text.splitlines()
    repaired = 0
    for index, line in enumerate(lines):
        if line.count('"') % 2 == 1:
            lines[index] = line.replace('"', "")
            repaired += 1
    return "\n".join(lines), repaired


def extract_csv(data, currency_default: str = "INR") -> ExtractionResult:
    """Parse a CSV export with flexible column mapping (§7)."""
    text = _decode(data) if isinstance(data, (bytes, bytearray)) else str(data)
    result = ExtractionResult(parser="csv")

    # A NUL byte means this is not text at all — a binary or corrupted upload.
    # Reported as a warning rather than allowed to raise `_csv.Error`, which
    # would surface to the user as a 500 (§7: errors must not expose internals).
    if "\x00" in text:
        text = text.replace("\x00", "")
        result.warnings.append("binary_content_detected")

    text, repaired = _repair_unbalanced_quotes(text)
    if repaired:
        result.warnings.append("unbalanced_quotes_repaired_on_%d_rows" % repaired)

    try:
        dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel

    try:
        reader = list(csv.reader(io.StringIO(text), dialect))
    except csv.Error as exc:
        # Never let a malformed file raise out of the parser.
        result.warnings.append("csv_parse_failed")
        logger_message = str(exc)[:80]
        result.rows_skipped.append((0, "csv_parse_failed:%s" % logger_message))
        return result

    if not reader:
        result.warnings.append("empty_file")
        return result

    # Find the header row — some banks prefix statements with metadata lines.
    header_idx, mapping = 0, {}
    for idx, row in enumerate(reader[:15]):
        candidate = _map_columns(row)
        if "date" in candidate and (
            "description" in candidate
            or "amount" in candidate
            or "debit" in candidate
        ):
            header_idx, mapping = idx, candidate
            break
    if not mapping:
        result.warnings.append("no_recognisable_header")
        return result

    result.currency = detect_currency(text[:2000], currency_default)

    for row_no, row in enumerate(reader[header_idx + 1:], start=header_idx + 2):
        result.rows_seen += 1
        if not any((cell or "").strip() for cell in row):
            continue

        def cell(name: str) -> Optional[str]:
            idx = mapping.get(name)
            if idx is None or idx >= len(row):
                return None
            return (row[idx] or "").strip() or None

        txn_date = parse_date(cell("date"))
        if txn_date is None:
            result.rows_skipped.append((row_no, "unparseable_date"))
            continue

        description = cell("description") or "(no description)"
        debit = parse_amount(cell("debit"))
        credit = parse_amount(cell("credit"))
        amount_col = parse_amount(cell("amount"))

        if debit is not None and debit != 0:
            amount, direction = abs(debit), Direction.DEBIT
        elif credit is not None and credit != 0:
            amount, direction = abs(credit), Direction.CREDIT
        elif amount_col is not None:
            # A single signed amount column: negative means money out.
            amount = abs(amount_col)
            direction = Direction.DEBIT if amount_col < 0 else Direction.CREDIT
        else:
            result.rows_skipped.append((row_no, "no_amount"))
            continue

        if amount == 0:
            result.rows_skipped.append((row_no, "zero_amount"))
            continue

        result.transactions.append(
            Transaction(
                date=txn_date,
                description=_MULTISPACE.sub(" ", description),
                amount=amount,
                direction=direction,
                balance=parse_amount(cell("balance")),
                reference=cell("reference"),
                currency=cell("currency") or result.currency,
                source_row=row_no,
                parser="csv",
                extraction_confidence=1.0,
            )
        )

    return result


def extract_xlsx(path_or_bytes) -> ExtractionResult:
    """XLSX via pandas (§7). Converts to CSV text and reuses the CSV parser."""
    try:
        import pandas as pd
    except ImportError:
        result = ExtractionResult(parser="xlsx")
        result.warnings.append("pandas_not_installed")
        return result

    frame = pd.read_excel(path_or_bytes, dtype=str)
    buffer = io.StringIO()
    frame.to_csv(buffer, index=False)
    result = extract_csv(buffer.getvalue())
    result.parser = "xlsx"
    for t in result.transactions:
        t.parser = "xlsx"
    return result


# ---------------------------------------------------------------------------
# PDF
# ---------------------------------------------------------------------------

#: A statement line: date, description, amounts. Deliberately permissive on the
#: description and strict on the numeric tail.
_PDF_LINE = re.compile(
    r"^(?P<date>\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{4}-\d{2}-\d{2}|\d{1,2}\s+\w{3}\s+\d{2,4})"
    r"\s+(?P<rest>.+)$"
)
_TRAILING_NUMBERS = re.compile(r"(\(?-?[\d,]+\.\d{2}\)?(?:\s*(?:CR|DR))?)")


def extract_pdf(path_or_bytes, password: Optional[str] = None) -> ExtractionResult:
    """Digital PDF extraction: pdfplumber tables first, then text lines (§7).

    Password-protected PDFs are supported when the caller supplies the password
    (§6.2). Scanned PDFs produce no text and are reported so the caller can route
    them to Textract/Gemini rather than silently returning nothing.
    """
    result = ExtractionResult(parser="pdf")
    pages_text: List[str] = []

    try:
        import pdfplumber

        opener = (
            pdfplumber.open(io.BytesIO(path_or_bytes), password=password)
            if isinstance(path_or_bytes, (bytes, bytearray))
            else pdfplumber.open(path_or_bytes, password=password)
        )
        with opener as pdf:
            for page_no, page in enumerate(pdf.pages, start=1):
                result.pages_processed += 1
                rows = _rows_from_tables(page)
                if rows:
                    _append_table_rows(result, rows, page_no)
                else:
                    pages_text.append(page.extract_text() or "")
        result.parser = "pdf:pdfplumber"
    except ImportError:
        try:
            import fitz  # PyMuPDF

            doc = (
                fitz.open(stream=path_or_bytes, filetype="pdf")
                if isinstance(path_or_bytes, (bytes, bytearray))
                else fitz.open(path_or_bytes)
            )
            if password and doc.needs_pass:
                doc.authenticate(password)
            for page_no, page in enumerate(doc, start=1):
                result.pages_processed += 1
                pages_text.append(page.get_text())
            result.parser = "pdf:pymupdf"
        except ImportError:
            result.warnings.append("no_pdf_library_installed")
            return result

    for page_no, text in enumerate(pages_text, start=1):
        _append_text_lines(result, text, page_no)

    if not result.transactions and result.pages_processed:
        # No text at all -> almost certainly a scan. §7 routes these onward.
        result.warnings.append("no_text_layer_probably_scanned_route_to_ocr")

    if result.transactions:
        result.currency = detect_currency(" ".join(pages_text[:2]) or "$")
    return result


def _rows_from_tables(page) -> List[Sequence[str]]:
    try:
        tables = page.extract_tables() or []
    except Exception:  # pragma: no cover - pdfplumber edge cases
        return []
    for table in tables:
        if table and len(table) > 1 and _map_columns([c or "" for c in table[0]]).get("date") is not None:
            return table
    return []


def _append_table_rows(result: ExtractionResult, rows: Sequence[Sequence[str]], page_no: int) -> None:
    mapping = _map_columns([c or "" for c in rows[0]])
    for row_no, row in enumerate(rows[1:], start=2):
        result.rows_seen += 1

        def cell(name):
            idx = mapping.get(name)
            if idx is None or idx >= len(row):
                return None
            return (row[idx] or "").strip() or None

        txn_date = parse_date(cell("date"))
        if txn_date is None:
            result.rows_skipped.append((row_no, "unparseable_date_in_table"))
            continue
        debit = parse_amount(cell("debit"))
        credit = parse_amount(cell("credit"))
        amount_col = parse_amount(cell("amount"))
        if debit:
            amount, direction = abs(debit), Direction.DEBIT
        elif credit:
            amount, direction = abs(credit), Direction.CREDIT
        elif amount_col:
            amount = abs(amount_col)
            direction = Direction.DEBIT if amount_col < 0 else Direction.CREDIT
        else:
            result.rows_skipped.append((row_no, "no_amount_in_table"))
            continue

        result.transactions.append(
            Transaction(
                date=txn_date,
                description=_MULTISPACE.sub(" ", cell("description") or "(no description)"),
                amount=amount,
                direction=direction,
                balance=parse_amount(cell("balance")),
                source_page=page_no,
                source_row=row_no,
                parser="pdf:table",
                extraction_confidence=0.95,
            )
        )


def _append_text_lines(result: ExtractionResult, text: str, page_no: int) -> None:
    """Layout-aware line parsing for statements without ruled tables."""
    previous_balance: Optional[Decimal] = None
    for line_no, line in enumerate(( text or "").splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        match = _PDF_LINE.match(line)
        if not match:
            continue
        result.rows_seen += 1

        txn_date = parse_date(match.group("date"))
        if txn_date is None:
            continue

        rest = match.group("rest")
        numbers = _TRAILING_NUMBERS.findall(rest)
        if not numbers:
            result.rows_skipped.append((line_no, "no_amount_on_line"))
            continue

        description = _MULTISPACE.sub(" ", _TRAILING_NUMBERS.sub("", rest)).strip(" -|")
        amounts = [parse_amount(n) for n in numbers]
        amounts = [a for a in amounts if a is not None]
        if not amounts:
            continue

        balance = None
        if len(amounts) >= 2:
            # Last number on a statement line is conventionally the balance.
            balance = amounts[-1]
            value = amounts[-2]
        else:
            value = amounts[0]

        # Infer direction from the balance delta when we have both balances.
        if balance is not None and previous_balance is not None:
            direction = Direction.CREDIT if balance > previous_balance else Direction.DEBIT
        else:
            direction = Direction.CREDIT if value < 0 else Direction.DEBIT
        previous_balance = balance if balance is not None else previous_balance

        result.transactions.append(
            Transaction(
                date=txn_date,
                description=description or "(no description)",
                amount=abs(value),
                direction=direction,
                balance=balance,
                source_page=page_no,
                source_row=line_no,
                parser="pdf:text",
                extraction_confidence=0.8,
                validation_warnings=(
                    [] if balance is not None else ["direction_inferred_without_balance"]
                ),
            )
        )


# ---------------------------------------------------------------------------
# SMS / email alerts (§7)
# ---------------------------------------------------------------------------

_SMS_PATTERNS = [
    re.compile(
        r"(?P<dc>debited|credited|spent|received|paid)\D{0,25}"
        r"(?P<cur>[$£€₹]|INR|USD|EUR|GBP)?\s?(?P<amt>[\d,]+\.?\d{0,2})",
        re.I,
    ),
    re.compile(
        r"(?P<cur>[$£€₹]|INR|USD|EUR|GBP)\s?(?P<amt>[\d,]+\.?\d{0,2})\D{0,25}"
        r"(?P<dc>debited|credited|spent|received|paid)",
        re.I,
    ),
]
_SMS_MERCHANT = re.compile(r"(?:at|to|from|via)\s+([A-Z0-9][A-Za-z0-9 &'._-]{2,30})")
_SMS_DATE = re.compile(r"(\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{4}-\d{2}-\d{2})")
_SMS_ACCOUNT = re.compile(r"(?:a/c|acct|account|card)\D{0,6}(?:x+|\*+)?(\d{3,4})", re.I)
# The separator class is punctuation/whitespace only. A broad `\D` here would be
# greedy over letters and swallow the alphabetic prefix of the reference itself,
# turning "Ref ABC123456" into "123456".
_SMS_REF = re.compile(r"(?:ref|utr|txn|reference)(?:\s*(?:no\.?|number)?\s*[:#-]?\s*)([A-Z0-9]{6,20})", re.I)
_SMS_BALANCE = re.compile(r"(?:bal|balance)\D{0,10}([\d,]+\.?\d{0,2})", re.I)

_CREDIT_WORDS = {"credited", "received"}


def extract_sms(text: str, default_date: Optional[date] = None) -> ExtractionResult:
    """Deterministic extraction from SMS/email alerts (§7).

    Runs before any model. Fields extracted: date/time, amount, direction,
    merchant, account mask, reference number, available balance where present.
    """
    result = ExtractionResult(parser="sms")
    for line_no, line in enumerate((text or "").splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        result.rows_seen += 1

        match = None
        for pattern in _SMS_PATTERNS:
            match = pattern.search(line)
            if match:
                break
        if not match:
            result.rows_skipped.append((line_no, "no_amount_pattern"))
            continue

        amount = parse_amount(match.group("amt"))
        if amount is None or amount == 0:
            result.rows_skipped.append((line_no, "unparseable_amount"))
            continue

        direction = (
            Direction.CREDIT
            if match.group("dc").lower() in _CREDIT_WORDS
            else Direction.DEBIT
        )

        merchant_match = _SMS_MERCHANT.search(line)
        merchant = merchant_match.group(1).strip() if merchant_match else None
        date_match = _SMS_DATE.search(line)
        txn_date = parse_date(date_match.group(1)) if date_match else default_date
        if txn_date is None:
            result.rows_skipped.append((line_no, "no_date"))
            continue

        account = _SMS_ACCOUNT.search(line)
        ref = _SMS_REF.search(line)
        balance = _SMS_BALANCE.search(line)

        symbol = match.groupdict().get("cur") or ""
        result.transactions.append(
            Transaction(
                date=txn_date,
                description=merchant or line[:60],
                amount=abs(amount),
                direction=direction,
                raw_merchant=merchant,
                balance=parse_amount(balance.group(1)) if balance else None,
                reference=ref.group(1) if ref else None,
                currency=CURRENCY_SYMBOLS.get(symbol, symbol.upper() or "INR"),
                source_row=line_no,
                parser="sms",
                extraction_confidence=0.75,
                # Account mask is deliberately not stored on the transaction —
                # §22 forbids retaining account numbers. Only the last 4 would be
                # available here and even that is dropped.
                validation_warnings=["account_mask_discarded"] if account else [],
            )
        )
    return result


# ---------------------------------------------------------------------------
# Deduplication across sources (§7)
# ---------------------------------------------------------------------------


def deduplicate(
    transactions: Iterable[Transaction],
) -> Tuple[List[Transaction], List[Transaction]]:
    """Dedupe on (date, amount, merchant, reference) per §7.

    Returns (kept, removed). Nothing is discarded silently — the caller shows the
    removed rows in the extraction review screen (§6.3, §8).
    """
    seen: Dict[tuple, Transaction] = {}
    kept: List[Transaction] = []
    removed: List[Transaction] = []
    for t in transactions:
        key = (
            t.date,
            t.amount,
            t.direction,
            (t.normalized_merchant or t.raw_merchant or t.description or "").lower()[:40],
            (t.reference or "").upper(),
        )
        if key in seen:
            removed.append(t)
            continue
        seen[key] = t
        kept.append(t)
    return kept, removed


def extract(data, filename: str = "", password: Optional[str] = None) -> ExtractionResult:
    """Dispatch on file extension. The single entry point used by the API."""
    lower = (filename or "").lower()
    if lower.endswith(".csv") or lower.endswith(".txt"):
        return extract_csv(data)
    if lower.endswith(".xlsx") or lower.endswith(".xls"):
        return extract_xlsx(data)
    if lower.endswith(".pdf"):
        return extract_pdf(data, password=password)
    # Unknown extension: sniff. PDFs start with %PDF.
    if isinstance(data, (bytes, bytearray)) and data[:4] == b"%PDF":
        return extract_pdf(data, password=password)
    return extract_csv(data)
