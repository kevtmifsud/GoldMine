#!/usr/bin/env python3
"""Generate all sample data for GoldMine development."""

import csv
import json
import os
import random
import uuid
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
STRUCTURED_DIR = DATA_DIR / "structured"
UNSTRUCTURED_DIR = DATA_DIR / "unstructured"

random.seed(42)


def ensure_dirs():
    for d in [
        STRUCTURED_DIR,
        UNSTRUCTURED_DIR / "reports",
        UNSTRUCTURED_DIR / "transcripts",
        UNSTRUCTURED_DIR / "data_exports",
        UNSTRUCTURED_DIR / "audio",
    ]:
        d.mkdir(parents=True, exist_ok=True)


# --------------- stocks.csv ---------------

SECTORS = {
    "Technology": ["Software", "Semiconductors", "IT Services", "Hardware"],
    "Healthcare": ["Pharmaceuticals", "Biotechnology", "Medical Devices", "Health Services"],
    "Financials": ["Banks", "Insurance", "Asset Management", "Fintech"],
    "Consumer Discretionary": ["Retail", "Automotive", "Apparel", "Restaurants"],
    "Industrials": ["Aerospace", "Machinery", "Transportation", "Construction"],
    "Energy": ["Oil & Gas", "Renewables", "Utilities"],
    "Communication Services": ["Media", "Telecom", "Entertainment"],
    "Consumer Staples": ["Food & Beverage", "Household Products"],
    "Materials": ["Chemicals", "Mining", "Metals"],
    "Real Estate": ["REITs", "Property Development"],
}

COMPANIES = [
    ("AAPL", "Apple Inc.", "Technology", "Hardware", 2800, "US", "NASDAQ"),
    ("MSFT", "Microsoft Corporation", "Technology", "Software", 2600, "US", "NASDAQ"),
    ("GOOGL", "Alphabet Inc.", "Communication Services", "Media", 1700, "US", "NASDAQ"),
    ("AMZN", "Amazon.com Inc.", "Consumer Discretionary", "Retail", 1500, "US", "NASDAQ"),
    ("NVDA", "NVIDIA Corporation", "Technology", "Semiconductors", 1200, "US", "NASDAQ"),
    ("META", "Meta Platforms Inc.", "Communication Services", "Media", 900, "US", "NASDAQ"),
    ("TSLA", "Tesla Inc.", "Consumer Discretionary", "Automotive", 750, "US", "NASDAQ"),
    ("BRK.B", "Berkshire Hathaway", "Financials", "Insurance", 780, "US", "NYSE"),
    ("UNH", "UnitedHealth Group", "Healthcare", "Health Services", 480, "US", "NYSE"),
    ("JNJ", "Johnson & Johnson", "Healthcare", "Pharmaceuticals", 420, "US", "NYSE"),
    ("V", "Visa Inc.", "Financials", "Fintech", 460, "US", "NYSE"),
    ("XOM", "Exxon Mobil Corp.", "Energy", "Oil & Gas", 430, "US", "NYSE"),
    ("JPM", "JPMorgan Chase & Co.", "Financials", "Banks", 490, "US", "NYSE"),
    ("WMT", "Walmart Inc.", "Consumer Staples", "Food & Beverage", 410, "US", "NYSE"),
    ("PG", "Procter & Gamble", "Consumer Staples", "Household Products", 360, "US", "NYSE"),
    ("MA", "Mastercard Inc.", "Financials", "Fintech", 380, "US", "NYSE"),
    ("HD", "Home Depot Inc.", "Consumer Discretionary", "Retail", 340, "US", "NYSE"),
    ("CVX", "Chevron Corporation", "Energy", "Oil & Gas", 290, "US", "NYSE"),
    ("MRK", "Merck & Co.", "Healthcare", "Pharmaceuticals", 270, "US", "NYSE"),
    ("LLY", "Eli Lilly and Co.", "Healthcare", "Pharmaceuticals", 580, "US", "NYSE"),
    ("ABBV", "AbbVie Inc.", "Healthcare", "Biotechnology", 260, "US", "NYSE"),
    ("PEP", "PepsiCo Inc.", "Consumer Staples", "Food & Beverage", 230, "US", "NASDAQ"),
    ("KO", "Coca-Cola Company", "Consumer Staples", "Food & Beverage", 250, "US", "NYSE"),
    ("COST", "Costco Wholesale", "Consumer Staples", "Food & Beverage", 310, "US", "NASDAQ"),
    ("AVGO", "Broadcom Inc.", "Technology", "Semiconductors", 400, "US", "NASDAQ"),
    ("TMO", "Thermo Fisher Scientific", "Healthcare", "Medical Devices", 210, "US", "NYSE"),
    ("MCD", "McDonald's Corp.", "Consumer Discretionary", "Restaurants", 200, "US", "NYSE"),
    ("CSCO", "Cisco Systems", "Technology", "Hardware", 195, "US", "NASDAQ"),
    ("ACN", "Accenture plc", "Technology", "IT Services", 190, "US", "NYSE"),
    ("ABT", "Abbott Laboratories", "Healthcare", "Medical Devices", 185, "US", "NYSE"),
    ("CRM", "Salesforce Inc.", "Technology", "Software", 240, "US", "NYSE"),
    ("ORCL", "Oracle Corporation", "Technology", "Software", 280, "US", "NYSE"),
    ("NFLX", "Netflix Inc.", "Communication Services", "Entertainment", 250, "US", "NASDAQ"),
    ("AMD", "Advanced Micro Devices", "Technology", "Semiconductors", 220, "US", "NASDAQ"),
    ("INTC", "Intel Corporation", "Technology", "Semiconductors", 130, "US", "NASDAQ"),
    ("IBM", "IBM Corporation", "Technology", "IT Services", 150, "US", "NYSE"),
    ("QCOM", "Qualcomm Inc.", "Technology", "Semiconductors", 170, "US", "NASDAQ"),
    ("TXN", "Texas Instruments", "Technology", "Semiconductors", 160, "US", "NASDAQ"),
    ("INTU", "Intuit Inc.", "Technology", "Software", 155, "US", "NASDAQ"),
    ("NOW", "ServiceNow Inc.", "Technology", "Software", 140, "US", "NYSE"),
    ("BA", "Boeing Company", "Industrials", "Aerospace", 120, "US", "NYSE"),
    ("CAT", "Caterpillar Inc.", "Industrials", "Machinery", 145, "US", "NYSE"),
    ("GE", "General Electric", "Industrials", "Aerospace", 160, "US", "NYSE"),
    ("RTX", "RTX Corporation", "Industrials", "Aerospace", 135, "US", "NYSE"),
    ("UPS", "United Parcel Service", "Industrials", "Transportation", 125, "US", "NYSE"),
    ("GS", "Goldman Sachs", "Financials", "Banks", 130, "US", "NYSE"),
    ("MS", "Morgan Stanley", "Financials", "Banks", 140, "US", "NYSE"),
    ("BLK", "BlackRock Inc.", "Financials", "Asset Management", 115, "US", "NYSE"),
    ("SCHW", "Charles Schwab", "Financials", "Fintech", 110, "US", "NYSE"),
    ("AXP", "American Express", "Financials", "Fintech", 150, "US", "NYSE"),
    ("DUK", "Duke Energy", "Energy", "Utilities", 80, "US", "NYSE"),
    ("NEE", "NextEra Energy", "Energy", "Renewables", 140, "US", "NYSE"),
    ("SLB", "Schlumberger Ltd.", "Energy", "Oil & Gas", 65, "US", "NYSE"),
    ("DIS", "Walt Disney Co.", "Communication Services", "Entertainment", 170, "US", "NYSE"),
    ("CMCSA", "Comcast Corp.", "Communication Services", "Telecom", 155, "US", "NASDAQ"),
    ("T", "AT&T Inc.", "Communication Services", "Telecom", 120, "US", "NYSE"),
    ("VZ", "Verizon Communications", "Communication Services", "Telecom", 155, "US", "NYSE"),
    ("NKE", "Nike Inc.", "Consumer Discretionary", "Apparel", 140, "US", "NYSE"),
    ("SBUX", "Starbucks Corp.", "Consumer Discretionary", "Restaurants", 105, "US", "NASDAQ"),
    ("LOW", "Lowe's Companies", "Consumer Discretionary", "Retail", 130, "US", "NYSE"),
    ("TGT", "Target Corporation", "Consumer Discretionary", "Retail", 65, "US", "NYSE"),
    ("FCX", "Freeport-McMoRan", "Materials", "Mining", 55, "US", "NYSE"),
    ("APD", "Air Products", "Materials", "Chemicals", 60, "US", "NYSE"),
    ("ECL", "Ecolab Inc.", "Materials", "Chemicals", 55, "US", "NYSE"),
    ("PLD", "Prologis Inc.", "Real Estate", "REITs", 110, "US", "NYSE"),
    ("AMT", "American Tower", "Real Estate", "REITs", 95, "US", "NYSE"),
    ("BABA", "Alibaba Group", "Consumer Discretionary", "Retail", 200, "CN", "NYSE"),
    ("TSM", "Taiwan Semiconductor", "Technology", "Semiconductors", 550, "TW", "NYSE"),
    ("ASML", "ASML Holding", "Technology", "Semiconductors", 280, "NL", "NASDAQ"),
    ("NVO", "Novo Nordisk", "Healthcare", "Pharmaceuticals", 380, "DK", "NYSE"),
    ("SAP", "SAP SE", "Technology", "Software", 200, "DE", "NYSE"),
    ("TM", "Toyota Motor Corp.", "Consumer Discretionary", "Automotive", 250, "JP", "NYSE"),
    ("SHEL", "Shell plc", "Energy", "Oil & Gas", 210, "GB", "NYSE"),
    ("RY", "Royal Bank of Canada", "Financials", "Banks", 140, "CA", "NYSE"),
    ("BHP", "BHP Group", "Materials", "Mining", 150, "AU", "NYSE"),
    ("UL", "Unilever plc", "Consumer Staples", "Household Products", 120, "GB", "NYSE"),
]


def generate_stocks():
    rows = []
    for ticker, name, sector, industry, mcap, country, exchange in COMPANIES:
        price = round(random.uniform(30, 600), 2)
        pe = round(random.uniform(8, 65), 1)
        high_52 = round(price * random.uniform(1.05, 1.45), 2)
        low_52 = round(price * random.uniform(0.55, 0.95), 2)
        div_yield = round(random.uniform(0, 4.5), 2)
        eps = round(price / pe, 2) if pe > 0 else 0
        revenue = round(mcap * random.uniform(0.15, 0.6), 1)
        rows.append({
            "ticker": ticker,
            "company_name": name,
            "sector": sector,
            "industry": industry,
            "market_cap_b": mcap,
            "pe_ratio": pe,
            "price": price,
            "52w_high": high_52,
            "52w_low": low_52,
            "dividend_yield": div_yield,
            "eps": eps,
            "revenue_b": revenue,
            "country": country,
            "exchange": exchange,
        })
    path = STRUCTURED_DIR / "stocks.csv"
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    print(f"  Created {path} ({len(rows)} rows)")


# --------------- people.csv ---------------

FIRST_NAMES = [
    "James", "Mary", "Robert", "Patricia", "John", "Jennifer", "Michael", "Linda",
    "David", "Elizabeth", "William", "Barbara", "Richard", "Susan", "Joseph", "Jessica",
    "Thomas", "Sarah", "Christopher", "Karen", "Daniel", "Lisa", "Matthew", "Nancy",
    "Anthony", "Betty", "Mark", "Margaret", "Donald", "Sandra", "Steven", "Ashley",
    "Andrew", "Dorothy", "Paul", "Kimberly", "Joshua", "Emily", "Kenneth", "Donna",
]
LAST_NAMES = [
    "Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller", "Davis",
    "Rodriguez", "Martinez", "Hernandez", "Lopez", "Gonzalez", "Wilson", "Anderson",
    "Thomas", "Taylor", "Moore", "Jackson", "Martin", "Lee", "Perez", "Thompson",
    "White", "Harris", "Sanchez", "Clark", "Ramirez", "Lewis", "Robinson", "Walker",
    "Young", "Allen", "King", "Wright", "Scott", "Torres", "Nguyen", "Hill", "Flores",
]
TITLES_EXEC = ["CEO", "CFO", "CTO", "COO", "President", "EVP", "SVP", "VP of Strategy"]
TITLES_ANALYST = ["Senior Analyst", "Research Analyst", "Portfolio Manager", "Associate PM", "Sector Head"]
ORGS_EXEC = [c[1] for c in COMPANIES[:30]]
ORGS_ANALYST = ["GoldMine Capital", "Apex Research", "Summit Advisors", "Pinnacle Partners", "Atlas Fund"]

TICKERS = [c[0] for c in COMPANIES]


def generate_people():
    rows = []
    used_names = set()
    pid = 1
    # 25 executives
    for _ in range(25):
        while True:
            name = f"{random.choice(FIRST_NAMES)} {random.choice(LAST_NAMES)}"
            if name not in used_names:
                used_names.add(name)
                break
        covered = random.sample(TICKERS, random.randint(1, 3))
        rows.append({
            "person_id": f"PER-{pid:03d}",
            "name": name,
            "title": random.choice(TITLES_EXEC),
            "organization": random.choice(ORGS_EXEC),
            "type": "executive",
            "tickers": ";".join(covered),
        })
        pid += 1
    # 15 analysts
    for _ in range(15):
        while True:
            name = f"{random.choice(FIRST_NAMES)} {random.choice(LAST_NAMES)}"
            if name not in used_names:
                used_names.add(name)
                break
        covered = random.sample(TICKERS, random.randint(2, 6))
        rows.append({
            "person_id": f"PER-{pid:03d}",
            "name": name,
            "title": random.choice(TITLES_ANALYST),
            "organization": random.choice(ORGS_ANALYST),
            "type": "analyst",
            "tickers": ";".join(covered),
        })
        pid += 1
    path = STRUCTURED_DIR / "people.csv"
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    print(f"  Created {path} ({len(rows)} rows)")


# --------------- datasets.csv ---------------

def generate_datasets():
    rows = [
        {"dataset_id": "DS-001", "name": "stocks", "display_name": "Stock Universe", "description": "Core stock universe with fundamentals", "record_count": 75, "id_field": "ticker", "category": "market_data"},
        {"dataset_id": "DS-002", "name": "people", "display_name": "People Directory", "description": "Executives and analysts", "record_count": 40, "id_field": "person_id", "category": "contacts"},
        {"dataset_id": "DS-003", "name": "sectors", "display_name": "Sector Reference", "description": "Sector and industry taxonomy", "record_count": 10, "id_field": "sector", "category": "reference"},
        {"dataset_id": "DS-004", "name": "watchlists", "display_name": "Watchlists", "description": "Portfolio manager watchlists", "record_count": 0, "id_field": "watchlist_id", "category": "portfolio"},
        {"dataset_id": "DS-005", "name": "meetings", "display_name": "Meeting Notes", "description": "Research meeting records", "record_count": 0, "id_field": "meeting_id", "category": "research"},
        {"dataset_id": "DS-006", "name": "ratings", "display_name": "Analyst Ratings", "description": "Internal analyst ratings and targets", "record_count": 0, "id_field": "rating_id", "category": "research"},
        {"dataset_id": "DS-007", "name": "portfolios", "display_name": "Portfolios", "description": "Portfolio holdings and allocations", "record_count": 0, "id_field": "portfolio_id", "category": "portfolio"},
        {"dataset_id": "DS-008", "name": "events", "display_name": "Corporate Events", "description": "Earnings calls, conferences, filings", "record_count": 0, "id_field": "event_id", "category": "market_data"},
        {"dataset_id": "DS-009", "name": "macro", "display_name": "Macro Indicators", "description": "Macroeconomic data points", "record_count": 0, "id_field": "indicator_id", "category": "market_data"},
        {"dataset_id": "DS-010", "name": "filings", "display_name": "SEC Filings", "description": "SEC filing metadata", "record_count": 0, "id_field": "filing_id", "category": "compliance"},
    ]
    path = STRUCTURED_DIR / "datasets.csv"
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    print(f"  Created {path} ({len(rows)} rows)")


# --------------- Unstructured files ---------------

def generate_transcripts():
    tickers_sample = random.sample(TICKERS[:30], 5)
    files = []
    for i, ticker in enumerate(tickers_sample, 1):
        company = next(c[1] for c in COMPANIES if c[0] == ticker)
        filename = f"{ticker}_Q4_2024_earnings.txt"
        content = f"""{company} ({ticker}) — Q4 2024 Earnings Call Transcript
Date: January {10 + i}, 2025
Participants: CEO, CFO, Head of IR

OPERATOR: Good morning and welcome to the {company} fourth quarter 2024 earnings call.

CEO: Thank you, operator. Good morning everyone. We're pleased to report strong results
for the fourth quarter and full year 2024. Revenue grew {random.randint(5, 25)}% year-over-year,
driven by {random.choice(['strong product demand', 'new customer acquisition', 'international expansion',
'pricing optimization', 'operational efficiency'])}.

Our key highlights for the quarter include:
- Revenue of ${random.randint(5, 80)}.{random.randint(1,9)} billion
- Operating margin expansion of {random.randint(50, 300)} basis points
- Free cash flow of ${random.randint(1, 20)}.{random.randint(1,9)} billion
- {random.choice(['Record customer additions', 'Strong pipeline growth', 'Successful product launches'])}

CFO: Thank you. Let me walk through the financial details...

[Transcript continues with Q&A session]

ANALYST Q&A:
Q: Can you provide more color on the margin expansion?
A: Certainly. We saw improvements across all segments...

Q: What's your outlook for 2025?
A: We're cautiously optimistic. Our guidance reflects...

[END OF TRANSCRIPT]
"""
        path = UNSTRUCTURED_DIR / "transcripts" / filename
        path.write_text(content)
        files.append({
            "file_id": f"FILE-{100 + i:03d}",
            "filename": filename,
            "path": f"transcripts/{filename}",
            "type": "transcript",
            "mime_type": "text/plain",
            "size_bytes": len(content.encode()),
            "tickers": [ticker],
            "date": f"2025-01-{10 + i:02d}",
            "description": f"{company} Q4 2024 earnings call transcript",
        })
    print(f"  Created {len(files)} transcripts")
    return files


def generate_reports():
    """Generate placeholder PDF reports (simple text files with .pdf extension for now)."""
    tickers_sample = random.sample(TICKERS[:20], 5)
    files = []
    for i, ticker in enumerate(tickers_sample, 1):
        company = next(c[1] for c in COMPANIES if c[0] == ticker)
        filename = f"{ticker}_research_report_2025.pdf"
        # Create a simple text placeholder - real PDF generation requires fpdf2
        path = UNSTRUCTURED_DIR / "reports" / filename
        content = f"[PDF Placeholder] Research Report: {company} ({ticker}) - January 2025\n"
        path.write_text(content)
        files.append({
            "file_id": f"FILE-{200 + i:03d}",
            "filename": filename,
            "path": f"reports/{filename}",
            "type": "report",
            "mime_type": "application/pdf",
            "size_bytes": len(content.encode()),
            "tickers": [ticker],
            "date": f"2025-01-{15 + i:02d}",
            "description": f"{company} research initiation report",
        })
    print(f"  Created {len(files)} reports")
    return files


def generate_data_exports():
    files = []
    exports = [
        ("sector_performance_2024.csv", "Sector performance summary for 2024"),
        ("top_holdings_q4.csv", "Top portfolio holdings Q4 2024"),
        ("dividend_schedule.csv", "Upcoming dividend schedule"),
    ]
    for i, (filename, desc) in enumerate(exports, 1):
        path = UNSTRUCTURED_DIR / "data_exports" / filename
        if "sector" in filename:
            content = "sector,return_ytd,return_q4,weight\nTechnology,32.5,8.2,28.5\nHealthcare,12.3,3.1,15.2\nFinancials,18.7,5.4,13.8\nEnergy,-5.2,-2.1,4.5\n"
        elif "holdings" in filename:
            content = "ticker,weight,shares,cost_basis,market_value\nAAPL,8.5,10000,145.20,182.50\nMSFT,7.2,5000,310.40,378.90\nNVDA,6.8,3000,420.10,520.30\n"
        else:
            content = "ticker,ex_date,pay_date,amount,frequency\nAAPL,2025-02-07,2025-02-13,0.25,quarterly\nMSFT,2025-02-20,2025-03-13,0.75,quarterly\n"
        path.write_text(content)
        files.append({
            "file_id": f"FILE-{300 + i:03d}",
            "filename": filename,
            "path": f"data_exports/{filename}",
            "type": "data_export",
            "mime_type": "text/csv",
            "size_bytes": len(content.encode()),
            "tickers": [],
            "date": f"2025-01-{20 + i:02d}",
            "description": desc,
        })
    print(f"  Created {len(files)} data exports")
    return files


def generate_audio():
    files = []
    filename = "AAPL_investor_day_2025.mp3"
    path = UNSTRUCTURED_DIR / "audio" / filename
    # Write a minimal placeholder
    path.write_bytes(b"\x00" * 1024)
    files.append({
        "file_id": "FILE-401",
        "filename": filename,
        "path": f"audio/{filename}",
        "type": "audio",
        "mime_type": "audio/mpeg",
        "size_bytes": 1024,
        "tickers": ["AAPL"],
        "date": "2025-01-25",
        "description": "Apple Investor Day 2025 recording (placeholder)",
    })
    print(f"  Created {len(files)} audio files")
    return files


def generate_manifest(all_files):
    manifest = {"files": all_files, "generated_at": "2025-01-30T00:00:00Z", "total_count": len(all_files)}
    path = UNSTRUCTURED_DIR / "files_manifest.json"
    with open(path, "w") as f:
        json.dump(manifest, f, indent=2)
    print(f"  Created {path} ({len(all_files)} files indexed)")


def main():
    print("Generating GoldMine sample data...")
    ensure_dirs()

    print("\nStructured data:")
    generate_stocks()
    generate_people()
    generate_datasets()

    print("\nUnstructured data:")
    all_files = []
    all_files.extend(generate_transcripts())
    all_files.extend(generate_reports())
    all_files.extend(generate_data_exports())
    all_files.extend(generate_audio())
    generate_manifest(all_files)

    print("\nDone! All sample data generated.")


if __name__ == "__main__":
    main()
