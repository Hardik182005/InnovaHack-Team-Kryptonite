"""Extraction and validation tests — spec §7, §8, §24.

Covers the §24 unit-test list items: CSV parsing, PDF extraction helpers,
debit/credit detection, currency detection, duplicate detection, transfer
matching.
"""

from __future__ import annotations

import os
from datetime import date
from decimal import Decimal

import pytest

from app.models.enums import Direction
from app.services import extraction, validation
from conftest import txn

DEMO_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "demo_data",
)


# --- amount parsing ---------------------------------------------------------


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("1,234.56", "1234.56"),
        ("$1,234.56", "1234.56"),
        ("₹1,234.56", "1234.56"),
        ("(1,234.56)", "-1234.56"),   # accounting negative
        ("-45.00", "-45.00"),
        ("1.234,56", "1234.56"),      # European separators
        ("500", "500.00"),
        ("120.50 CR", "120.50"),
        ("120.50 DR", "-120.50"),
    ],
)
def test_parse_amount(raw, expected):
    assert extraction.parse_amount(raw) == Decimal(expected)


@pytest.mark.parametrize("raw", ["", None, "abc", "--"])
def test_parse_amount_rejects_garbage(raw):
    assert extraction.parse_amount(raw) is None


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("2026-03-14", date(2026, 3, 14)),
        ("14/03/2026", date(2026, 3, 14)),
        ("03-14-2026", date(2026, 3, 14)),
        ("14 Mar 2026", date(2026, 3, 14)),
        ("Mar 14, 2026", date(2026, 3, 14)),
    ],
)
def test_parse_date(raw, expected):
    assert extraction.parse_date(raw) == expected


def test_parse_date_rejects_garbage():
    assert extraction.parse_date("not a date") is None


@pytest.mark.parametrize(
    "text,expected",
    [("Total $45.00", "USD"), ("Total ₹45", "INR"), ("Balance EUR 10", "EUR")],
)
def test_currency_detection(text, expected):
    assert extraction.detect_currency(text) == expected


# --- CSV ---------------------------------------------------------------------


def test_csv_with_debit_credit_columns():
    csv_text = (
        "Transaction Date,Narration,Debit,Credit,Balance\n"
        "2026-01-01,ACME PAYROLL,,3200.00,3200.00\n"
        "2026-01-03,GREENFIELD RENT,1450.00,,1750.00\n"
    )
    result = extraction.extract_csv(csv_text)
    assert len(result.transactions) == 2
    assert result.transactions[0].direction is Direction.CREDIT
    assert result.transactions[1].direction is Direction.DEBIT
    assert result.transactions[1].amount == Decimal("1450.00")
    assert result.transactions[1].balance == Decimal("1750.00")


def test_csv_with_single_signed_amount_column():
    """A negative amount means money out."""
    csv_text = (
        "Date,Description,Amount\n"
        "2026-01-01,SALARY,3200.00\n"
        "2026-01-03,RENT,-1450.00\n"
    )
    result = extraction.extract_csv(csv_text)
    assert result.transactions[0].direction is Direction.CREDIT
    assert result.transactions[1].direction is Direction.DEBIT
    assert result.transactions[1].amount == Decimal("1450.00")


def test_csv_column_aliases_are_honoured():
    """§7 lists narration/particulars/withdrawal/deposit as valid headers."""
    csv_text = (
        "Posting Date,Particulars,Withdrawal,Deposit\n"
        "2026-02-05,SOME SHOP,25.00,\n"
    )
    result = extraction.extract_csv(csv_text)
    assert len(result.transactions) == 1
    assert result.transactions[0].description == "SOME SHOP"


def test_csv_skips_preamble_rows_before_header():
    csv_text = (
        "SYNTHETIC DEMO DATA\n"
        "\n"
        "Transaction Date,Narration,Debit,Credit,Balance\n"
        "2026-01-03,RENT,1450.00,,100.00\n"
    )
    result = extraction.extract_csv(csv_text)
    assert len(result.transactions) == 1


def test_csv_records_skipped_rows_rather_than_dropping_them():
    """§8: never silently drop a transaction."""
    csv_text = (
        "Date,Description,Amount\n"
        "2026-01-01,GOOD,10.00\n"
        "not-a-date,BAD,10.00\n"
        "2026-01-02,NOAMOUNT,\n"
    )
    result = extraction.extract_csv(csv_text)
    assert len(result.transactions) == 1
    assert len(result.rows_skipped) == 2
    reasons = {reason for _, reason in result.rows_skipped}
    assert reasons == {"unparseable_date", "no_amount"}


def test_csv_unrecognisable_header_warns():
    result = extraction.extract_csv("alpha,beta\n1,2\n")
    assert "no_recognisable_header" in result.warnings


# --- SMS ---------------------------------------------------------------------


def test_sms_extraction():
    text = (
        "Your a/c XX4417 debited $45.20 at STARBUCKS on 14/03/2026. Ref ABC123456. Bal 980.10\n"
        "Your a/c XX4417 credited $3200.00 from ACME PAYROLL on 28/03/2026.\n"
    )
    result = extraction.extract_sms(text)
    assert len(result.transactions) == 2
    debit, credit = result.transactions
    assert debit.direction is Direction.DEBIT
    assert debit.amount == Decimal("45.20")
    assert debit.reference == "ABC123456"
    assert debit.balance == Decimal("980.10")
    assert credit.direction is Direction.CREDIT


def test_sms_never_stores_the_account_mask():
    """§22 forbids retaining account numbers, even the last four digits."""
    text = "Your a/c XX4417 debited $45.20 at SHOP on 14/03/2026."
    result = extraction.extract_sms(text)
    t = result.transactions[0]
    assert "4417" not in (t.description or "")
    assert "4417" not in (t.raw_merchant or "")
    assert "4417" not in (t.reference or "")
    assert "account_mask_discarded" in t.validation_warnings


# --- deduplication (§7) ------------------------------------------------------


def test_deduplicate_across_sources():
    a = txn(date(2026, 1, 5), "STARBUCKS", "4.50", merchant="Starbucks", reference="R1")
    b = txn(date(2026, 1, 5), "STARBUCKS", "4.50", merchant="Starbucks", reference="R1")
    c = txn(date(2026, 1, 6), "STARBUCKS", "4.50", merchant="Starbucks", reference="R2")
    kept, removed = extraction.deduplicate([a, b, c])
    assert len(kept) == 2
    assert len(removed) == 1  # returned, not silently discarded


# --- validation (§8) ---------------------------------------------------------


def test_validation_flags_duplicates():
    rows = [
        txn(date(2026, 1, 5), "SHOP", "10.00"),
        txn(date(2026, 1, 5), "SHOP", "10.00"),
    ]
    report = validation.validate(rows)
    assert report.duplicate_groups
    assert all("possible_duplicate" in r.validation_warnings for r in rows)


def test_validation_matches_transfer_pairs():
    rows = [
        txn(date(2026, 1, 25), "TRANSFER OUT", "200.00", direction=Direction.DEBIT),
        txn(date(2026, 1, 25), "TRANSFER IN", "200.00", direction=Direction.CREDIT),
    ]
    report = validation.validate(rows)
    assert len(report.transfer_pairs) == 1


def test_validation_reconciles_running_balance():
    rows = [
        txn(date(2026, 1, 1), "SALARY", "1000", direction=Direction.CREDIT, balance="1000"),
        txn(date(2026, 1, 2), "RENT", "400", balance="600"),
    ]
    report = validation.validate(rows)
    assert report.balance_reconciles is True
    assert report.opening_balance == Decimal("1000.00")
    assert report.closing_balance == Decimal("600.00")


def test_validation_detects_balance_mismatch():
    rows = [
        txn(date(2026, 1, 1), "SALARY", "1000", direction=Direction.CREDIT, balance="1000"),
        txn(date(2026, 1, 2), "RENT", "400", balance="999"),  # should be 600
    ]
    report = validation.validate(rows)
    assert report.balance_reconciles is False
    assert "balance_does_not_reconcile" in rows[1].validation_warnings


def test_validation_detects_reversed_debit_credit():
    """A balance that moved the wrong way by exactly the amount is a sign flip."""
    rows = [
        txn(date(2026, 1, 1), "SALARY", "1000", direction=Direction.CREDIT, balance="1000"),
        txn(date(2026, 1, 2), "RENT", "400", direction=Direction.CREDIT, balance="600"),
    ]
    report = validation.validate(rows)
    assert "reversed_debit_credit_suspected" in rows[1].validation_warnings


def test_validation_flags_mixed_currencies():
    rows = [
        txn(date(2026, 1, 1), "A", "10", currency="USD"),
        txn(date(2026, 1, 2), "B", "10", currency="EUR"),
    ]
    report = validation.validate(rows)
    assert "mixed_currencies_detected" in report.statement_warnings


def test_validation_flags_empty_statement():
    report = validation.validate([])
    assert "no_transactions_extracted" in report.statement_warnings


# --- the generated demo statement (§23) --------------------------------------

demo_csv = pytest.mark.skipif(
    not os.path.exists(os.path.join(DEMO_DIR, "demo_statement.csv")),
    reason="run scripts/generate_demo_statement.py first",
)
demo_pdf = pytest.mark.skipif(
    not os.path.exists(os.path.join(DEMO_DIR, "demo_statement.pdf")),
    reason="run scripts/generate_demo_statement.py first",
)


@demo_csv
def test_demo_csv_parses_cleanly_and_reconciles():
    with open(os.path.join(DEMO_DIR, "demo_statement.csv"), "rb") as fh:
        result = extraction.extract(fh.read(), "demo_statement.csv")
    assert len(result.transactions) > 150
    assert result.rows_skipped == []
    report = validation.validate(result.transactions)
    assert report.balance_reconciles is True


@demo_pdf
def test_demo_pdf_has_a_readable_text_layer():
    """The generated PDF must be a real digital PDF, not an image."""
    pytest.importorskip("pdfplumber")
    with open(os.path.join(DEMO_DIR, "demo_statement.pdf"), "rb") as fh:
        result = extraction.extract(fh.read(), "demo_statement.pdf")
    assert result.pages_processed > 0
    assert len(result.transactions) > 150
    assert "no_text_layer_probably_scanned_route_to_ocr" not in result.warnings


@demo_csv
@demo_pdf
def test_demo_csv_and_pdf_agree():
    """Both formats of the same statement must extract the same transactions."""
    pytest.importorskip("pdfplumber")
    with open(os.path.join(DEMO_DIR, "demo_statement.csv"), "rb") as fh:
        csv_result = extraction.extract(fh.read(), "demo_statement.csv")
    with open(os.path.join(DEMO_DIR, "demo_statement.pdf"), "rb") as fh:
        pdf_result = extraction.extract(fh.read(), "demo_statement.pdf")
    assert len(csv_result.transactions) == len(pdf_result.transactions)
    csv_total = sum(t.amount for t in csv_result.transactions)
    pdf_total = sum(t.amount for t in pdf_result.transactions)
    assert csv_total == pdf_total
