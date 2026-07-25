#!/usr/bin/env python3
"""Generate the synthetic demo statement — spec §23.

Every element §23 requires is present, and the data is shaped so the demo tells
the SafeSpare story: raw round-ups look generous, but rent + insurance + EMI land
before payday, so the safe contribution is materially smaller.

ALL DATA IS SYNTHETIC. No real person, account or merchant relationship is
represented. Amounts, names and account masks are invented.

Usage:
    python3 scripts/generate_demo_statement.py [--out demo_data]
"""

from __future__ import annotations

import argparse
import csv
import os
import random
from datetime import date, timedelta
from decimal import Decimal

SYNTHETIC_BANNER = "SYNTHETIC DEMO DATA - NOT A REAL BANK STATEMENT"

# Deterministic output so the demo is identical on every machine and every run.
random.seed(20260725)

START = date(2026, 1, 1)
MONTHS = 6

#: Payday is the 28th, so rent (3rd), insurance (6th) and the loan EMI (8th) all
#: fall BEFORE the next salary. That ordering is the entire point of the demo:
#: raw round-up maths looks generous, but the money is already spoken for.
PAYDAY = 28
MONTHLY_INCOME = Decimal("3200.00")

#: The closing balance is pinned rather than left to drift, so the demo tells the
#: same story on every machine: enough to clear the safety buffer by a little,
#: not enough to make the round-up cap irrelevant. The opening balance is solved
#: backwards from this figure.
TARGET_CLOSING_BALANCE = Decimal("2880.00")


def _month_start(index: int) -> date:
    year = START.year + (START.month - 1 + index) // 12
    month = (START.month - 1 + index) % 12 + 1
    return date(year, month, 1)


def _d(index: int, day: int) -> date:
    base = _month_start(index)
    return base + timedelta(days=day - 1)


def build_rows():
    """Return (date, description, debit, credit) tuples, unsorted."""
    rows = []

    def debit(d, desc, amount):
        rows.append((d, desc, Decimal(str(amount)), None))

    def credit(d, desc, amount):
        rows.append((d, desc, None, Decimal(str(amount))))

    for m in range(MONTHS):
        # --- income -------------------------------------------------------
        credit(_d(m, PAYDAY), "ACME ANALYTICS PAYROLL DIRECT DEPOSIT", str(MONTHLY_INCOME))

        # --- essentials, deliberately landing before the next payday ------
        debit(_d(m, 3), "GREENFIELD PROPERTIES RENT", "1450.00")
        debit(_d(m, 6), "SECURELIFE INSURANCE PREMIUM", "128.00")
        debit(_d(m, 8), "FIRSTBANK AUTO LOAN EMI 55212", "312.40")
        debit(_d(m, 11), "CITY POWER + WATER UTILITY BILL", str(88 + random.randint(-14, 26)))

        # --- groceries (essential, variable) ------------------------------
        for day in (4, 12, 19, 26):
            debit(_d(m, day), "CORNER SUPERMARKET", str(random.randint(42, 96)) + ".%02d" % random.randint(0, 99))

        # --- subscriptions ------------------------------------------------
        debit(_d(m, 14), "NETFLIX.COM SUBSCRIPTION", "15.99")
        # Silent price increase from month 3 onward (§23 "subscription price increase")
        debit(_d(m, 17), "CLOUDVAULT STORAGE PLUS", "9.99" if m < 3 else "13.99")
        # Duplicate cloud-storage service (§23 "duplicate cloud-storage service")
        debit(_d(m, 21), "DROPBOX PLUS ANNUALBILL MONTHLY", "11.99")
        # Gym — the demo's "user confirms unused" subscription
        debit(_d(m, 9), "PEAK FITNESS GYM MEMBERSHIP", "49.00")
        debit(_d(m, 23), "ADOBE CREATIVE CLOUD", "22.99")

        # --- discretionary: the spending that generates the round-ups -----
        # Fractional cents are drawn deliberately so round-ups are non-trivial;
        # a statement of whole-dollar amounts would produce no spare change at all.
        for day in (2, 4, 5, 7, 10, 12, 13, 15, 16, 18, 19, 22, 24, 26, 27):
            desc = random.choice(
                [
                    "UBER EATS DELIVERY",
                    "STARBUCKS COFFEE",
                    "THE DAILY GRIND CAFE",
                    "PIZZA PLACE #221",
                    "UBER TRIP",
                    "SHELL FUEL",
                    "AMZN MKTP US*2K4LP",
                    "NORTHGATE RETAIL PARK",
                ]
            )
            amount = Decimal(str(random.randint(18, 78))) + Decimal(
                str(random.choice([0.10, 0.25, 0.30, 0.45, 0.60, 0.75, 0.85, 0.90, 0.99]))
            )
            debit(_d(m, day), desc, str(amount))

        # --- internal transfer (§23) --------------------------------------
        debit(_d(m, 25), "TRANSFER TO OWN SAVINGS ACCOUNT", "200.00")
        credit(_d(m, 25), "TRANSFER FROM CURRENT ACCOUNT", "200.00")

        # --- unknown merchant (§23) ---------------------------------------
        debit(_d(m, 20), "QX7 TRADING 99231", "18.75")

    # --- one-off refund (§23) --------------------------------------------
    credit(_d(2, 16), "REFUND AMZN MKTP US ORDER 114-22", "34.60")

    # --- an ATM withdrawal and a bank charge, both round-up excluded ------
    debit(_d(1, 15), "ATM CASH WITHDRAWAL", "100.00")
    debit(_d(4, 28), "MONTHLY ACCOUNT SERVICE CHARGE", "4.50")

    return rows


def with_running_balance(rows):
    """Sort chronologically and attach a reconciling running balance.

    The opening balance is solved backwards from TARGET_CLOSING_BALANCE so the
    statement always ends in the same cash position regardless of how the random
    discretionary amounts fell. Without this the demo's Safe Spare figure would
    drift between runs and the story would sometimes not land.

    Returns (rows_with_balance, opening_balance).
    """
    rows = sorted(rows, key=lambda r: r[0])
    net = sum(
        ((cr or Decimal("0")) - (dr or Decimal("0"))) for _, _, dr, cr in rows
    )
    opening = (TARGET_CLOSING_BALANCE - net).quantize(Decimal("0.01"))

    balance = opening
    out = []
    for d, desc, dr, cr in rows:
        balance = balance + (cr or Decimal("0")) - (dr or Decimal("0"))
        out.append((d, desc, dr, cr, balance.quantize(Decimal("0.01"))))
    return out, opening


def write_csv(rows, path):
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow([SYNTHETIC_BANNER])
        writer.writerow([])
        writer.writerow(
            ["Transaction Date", "Narration", "Debit", "Credit", "Balance"]
        )
        for d, desc, dr, cr, bal in rows:
            writer.writerow(
                [
                    d.isoformat(),
                    desc,
                    "" if dr is None else "%.2f" % dr,
                    "" if cr is None else "%.2f" % cr,
                    "%.2f" % bal,
                ]
            )
    return path


def _pdf_escape(text):
    return text.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")


def write_pdf(rows, path, opening_balance):
    """Emit a real digital PDF with a text layer, using only the stdlib.

    reportlab would be tidier, but keeping this dependency-free means the demo
    statement can always be regenerated — including inside a minimal container —
    and the output still has a genuine text layer for pdfplumber to read.
    """
    lines_per_page = 46
    pages = []
    header = [
        SYNTHETIC_BANNER,
        "",
        "NORTHWIND COMMUNITY BANK (fictional)",
        "Account: Everyday Checking  ****4417   Currency: USD",
        "Statement period: %s to %s" % (rows[0][0].isoformat(), rows[-1][0].isoformat()),
        "Opening balance: %.2f" % opening_balance,
        "",
        "%-12s %-42s %12s %12s %12s" % ("DATE", "DESCRIPTION", "DEBIT", "CREDIT", "BALANCE"),
        "-" * 94,
    ]

    body = [
        "%-12s %-42s %12s %12s %12s"
        % (
            d.isoformat(),
            desc[:42],
            "" if dr is None else "%.2f" % dr,
            "" if cr is None else "%.2f" % cr,
            "%.2f" % bal,
        )
        for d, desc, dr, cr, bal in rows
    ]

    chunk = lines_per_page - len(header)
    for i in range(0, len(body), chunk):
        pages.append(header + body[i : i + chunk])

    objects = []
    # 1 catalog, 2 pages tree, 3 font, then per page: page obj + content stream
    page_obj_ids = [4 + 2 * i for i in range(len(pages))]

    objects.append((1, "<< /Type /Catalog /Pages 2 0 R >>"))
    kids = " ".join("%d 0 R" % pid for pid in page_obj_ids)
    objects.append(
        (2, "<< /Type /Pages /Count %d /Kids [%s] >>" % (len(pages), kids))
    )
    objects.append(
        (3, "<< /Type /Font /Subtype /Type1 /BaseFont /Courier >>")
    )

    for idx, page_lines in enumerate(pages):
        pid = page_obj_ids[idx]
        cid = pid + 1
        objects.append(
            (
                pid,
                "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 792 612] "
                "/Resources << /Font << /F1 3 0 R >> >> /Contents %d 0 R >>" % cid,
            )
        )
        text_ops = ["BT", "/F1 8 Tf", "10 580 Td", "9.6 TL"]
        for line in page_lines:
            text_ops.append("(%s) Tj T*" % _pdf_escape(line))
        text_ops.append("ET")
        stream = "\n".join(text_ops)
        objects.append(
            (
                cid,
                "<< /Length %d >>\nstream\n%s\nendstream" % (len(stream), stream),
            )
        )

    out = bytearray(b"%PDF-1.4\n")
    offsets = {}
    for num, payload in sorted(objects):
        offsets[num] = len(out)
        out += ("%d 0 obj\n%s\nendobj\n" % (num, payload)).encode("latin-1")

    xref_pos = len(out)
    max_obj = max(offsets) + 1
    out += ("xref\n0 %d\n" % max_obj).encode()
    out += b"0000000000 65535 f \n"
    for num in range(1, max_obj):
        out += ("%010d 00000 n \n" % offsets.get(num, 0)).encode()
    out += (
        "trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n"
        % (max_obj, xref_pos)
    ).encode()

    with open(path, "wb") as fh:
        fh.write(bytes(out))
    return path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="demo_data", help="output directory")
    args = parser.parse_args()

    os.makedirs(args.out, exist_ok=True)
    rows, opening = with_running_balance(build_rows())

    csv_path = write_csv(rows, os.path.join(args.out, "demo_statement.csv"))
    pdf_path = write_pdf(rows, os.path.join(args.out, "demo_statement.pdf"), opening)

    debits = sum((r[2] or Decimal("0")) for r in rows)
    credits = sum((r[3] or Decimal("0")) for r in rows)
    print("%s" % SYNTHETIC_BANNER)
    print("rows:            %d" % len(rows))
    print("period:          %s to %s" % (rows[0][0], rows[-1][0]))
    print("total debits:    %.2f" % debits)
    print("total credits:   %.2f" % credits)
    print("opening balance: %.2f" % opening)
    print("closing balance: %.2f" % rows[-1][4])
    print("avg monthly surplus: %.2f" % ((credits - debits) / MONTHS))
    print("written:         %s" % csv_path)
    print("written:         %s" % pdf_path)


if __name__ == "__main__":
    main()
