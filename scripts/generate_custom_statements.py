import csv
import os
import random
from datetime import date, timedelta
from decimal import Decimal

# Setup paths
DEMO_DATA_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "demo_data",
)
os.makedirs(DEMO_DATA_DIR, exist_ok=True)

# Seed for reproducibility
random.seed(42)

START_DATE = date(2026, 1, 1)
MONTHS = 3

SYNTHETIC_BANNER = "SYNTHETIC DEMO DATA - NOT A REAL BANK STATEMENT"

def _pdf_escape(text):
    return text.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")

def write_pdf(rows, path, opening_balance, bank_name, account_mask):
    """Emit a real digital PDF with a text layer, using only the stdlib."""
    lines_per_page = 46
    pages = []
    header = [
        SYNTHETIC_BANNER,
        "",
        bank_name,
        f"Account: Savings A/c  {account_mask}   Currency: INR",
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

def with_running_balance(rows, target_closing):
    rows = sorted(rows, key=lambda r: r[0])
    net = sum(((cr or Decimal("0")) - (dr or Decimal("0"))) for _, _, dr, cr in rows)
    opening = (target_closing - net).quantize(Decimal("0.01"))
    
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
        writer.writerow(["Transaction Date", "Narration", "Debit", "Credit", "Balance"])
        for d, desc, dr, cr, bal in rows:
            writer.writerow([
                d.isoformat(),
                desc,
                "" if dr is None else "%.2f" % dr,
                "" if cr is None else "%.2f" % cr,
                "%.2f" % bal,
            ])
    return path

def generate_avi_statement():
    raw_rows = []
    
    for m in range(MONTHS):
        m_start = date(START_DATE.year, START_DATE.month + m, 1)
        
        # 1. Salary Credit (28th)
        raw_rows.append((m_start.replace(day=28), "TATA CONSULTANCY SERVICES PAYROLL", None, Decimal("75000.00")))
        
        # 2. Rent Debit (3rd) - Essential
        raw_rows.append((m_start.replace(day=3), "HOUSING SOCIETY MONTHLY RENT TRANSFER", Decimal("22000.00"), None))
        
        # 3. Education Loan EMI (5th) - Essential
        raw_rows.append((m_start.replace(day=5), "HDFC BANK EDUCATION LOAN EMI", Decimal("11500.00"), None))
        
        # 4. Life Insurance ECS (7th) - Essential
        raw_rows.append((m_start.replace(day=7), "LIC OF INDIA PREMIUM AUTOPAY", Decimal("3500.00"), None))
        
        # 5. Utilities (9th) - Essential
        util_amt = Decimal(f"{2800 + random.randint(-200, 500)}.00")
        raw_rows.append((m_start.replace(day=9), "MSEDCL ELECTRICITY BILL PAYMENT", util_amt, None))
        
        # 6. Groceries (Weekly: 4th, 11th, 18th, 25th)
        for d in [4, 11, 18, 25]:
            g_amt = Decimal(f"{2400 + random.randint(-400, 800)}.{random.randint(10, 99)}")
            raw_rows.append((m_start.replace(day=d), "STAR BAZAR SUPERMARKET", g_amt, None))
            
        # 7. Discretionary Daily Spends (with roundups)
        spends = [
            (10, "BLUE TOKAI COFFEE ROASTERS", "185.50"),
            (12, "UBER INDIA RIDE", "320.20"),
            (15, "NETFLIX ENTERTAINMENT", "649.00"),
            (16, "INDEPENDENT BOOKSTORE", "420.40"),
            (20, "PHARMACY MEDICAL PURCHASE", "380.10"),
            (22, "SWIGGY DELIVERY FOOD", "510.80"),
            (27, "JIO INFOCOMM RECHARGE", "299.00")
        ]
        for day, desc, amt_str in spends:
            raw_rows.append((m_start.replace(day=day), desc, Decimal(amt_str), None))
            
    rows, opening = with_running_balance(raw_rows, Decimal("50000.00"))
    
    csv_path = os.path.join(DEMO_DATA_DIR, "sbi_avi_statement.csv")
    pdf_path = os.path.join(DEMO_DATA_DIR, "sbi_avi_statement.pdf")
    
    write_csv(rows, csv_path)
    write_pdf(rows, pdf_path, opening, "STATE BANK OF INDIA (fictional)", "****1234")
    return csv_path, pdf_path

def generate_hardik_statement():
    raw_rows = []
    
    for m in range(MONTHS):
        m_start = date(START_DATE.year, START_DATE.month + m, 1)
        
        # 1. Salary Credit (28th)
        raw_rows.append((m_start.replace(day=28), "RELIANCE INDUSTRIES PAYROLL", None, Decimal("55000.00")))
        
        # 2. Rent Debit (3rd) - Essential (much lower)
        raw_rows.append((m_start.replace(day=3), "PG ACCOMMODATION MONTHLY RENT", Decimal("12000.00"), None))
        
        # 3. Utilities / Broadband (10th) - Essential
        raw_rows.append((m_start.replace(day=10), "ACT FIBERNET INTERNET BILL", Decimal("1500.00"), None))
        
        # 4. Groceries (Weekly: 4th, 11th, 18th, 25th)
        for d in [4, 11, 18, 25]:
            g_amt = Decimal(f"{1200 + random.randint(-200, 400)}.{random.randint(10, 99)}")
            raw_rows.append((m_start.replace(day=d), "DMART GROCERY STORE", g_amt, None))
            
        # 5. High Discretionary / Leaky subscriptions / roundups
        spends = [
            (5, "STARBUCKS COFFEE", "280.40"),
            (7, "ZOMATO RESTAURANT INC", "420.30"),
            (9, "BOOKMYSHOW ENTERTAINMENT", "350.20"),
            (12, "NETFLIX ENTERTAINMENT", "649.00"),
            (14, "NETFLIX MOBILE APP", "199.00"),
            (15, "SPOTIFY PREMIUM SERVICES", "119.00"),
            (17, "UBER DRIVER RIDE", "180.70"),
            (20, "SWIGGY DELIVERY FOOD", "380.90"),
            (21, "YOUTUBE PREMIUM SUBSCRIPTION", "129.00"),
            (22, "AMAZON SELLER INDIA", "890.60"),
            (24, "LOCAL TAPROOM BREWERY", "1250.00"),
            (26, "ZOMATO RESTAURANT INC", "290.10")
        ]
        for day, desc, amt_str in spends:
            raw_rows.append((m_start.replace(day=day), desc, Decimal(amt_str), None))
            
    rows, opening = with_running_balance(raw_rows, Decimal("35000.00"))
    
    csv_path = os.path.join(DEMO_DATA_DIR, "hdfc_hardik_statement.csv")
    pdf_path = os.path.join(DEMO_DATA_DIR, "hdfc_hardik_statement.pdf")
    
    write_csv(rows, csv_path)
    write_pdf(rows, pdf_path, opening, "HDFC BANK OF INDIA (fictional)", "****5678")
    return csv_path, pdf_path

if __name__ == "__main__":
    avi_csv, avi_pdf = generate_avi_statement()
    hardik_csv, hardik_pdf = generate_hardik_statement()
    print(f"Successfully generated custom statement CSV and PDF:\n- {avi_csv}\n- {avi_pdf}\n- {hardik_csv}\n- {hardik_pdf}")
