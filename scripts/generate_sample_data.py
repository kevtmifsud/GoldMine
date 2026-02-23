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
        UNSTRUCTURED_DIR / "notes",
    ]:
        d.mkdir(parents=True, exist_ok=True)


# --------------- stocks.csv ---------------

SECTORS = {
    "Technology": ["Software", "Semiconductors", "Hardware", "IT Services", "Networking",
                    "Electronics", "Semiconductor Equipment", "Internet Services"],
    "Healthcare": ["Pharmaceuticals", "Biotechnology", "Medical Devices", "Health Services",
                    "Life Sciences", "Health Insurance", "Health Tech"],
    "Financials": ["Banks", "Insurance", "Asset Management", "Fintech", "Investment Banking",
                    "Consumer Finance", "Financial Services", "Conglomerates"],
    "Consumer Discretionary": ["Retail", "Automotive", "Apparel", "Restaurants", "Hospitality",
                               "Entertainment", "Construction", "Distribution", "Consumer Services"],
    "Industrials": ["Aerospace", "Machinery", "Transportation", "Construction",
                     "Building Products", "Electrical Equipment", "Business Services",
                     "Environmental Services", "Consulting", "Distribution", "Conglomerates"],
    "Energy": ["Oil & Gas", "Oil & Gas Services", "Power"],
    "Communication Services": ["Media", "Telecom", "Entertainment", "Advertising"],
    "Consumer Staples": ["Food & Beverage", "Household Products", "Retail", "Personal Care",
                          "Tobacco", "Agriculture", "Beverages", "Food Distribution"],
    "Utilities": ["Electric Utilities", "Utilities", "Gas Utilities", "Water Utilities", "Power"],
    "Materials": ["Chemicals", "Mining", "Metals", "Packaging", "Building Materials"],
    "Real Estate": ["REITs", "Real Estate Services"],
}

COMPANIES = [
    ("MMM", "3M", "Industrials", "Conglomerates", 40, "US", "NYSE"),
    ("AOS", "A. O. Smith", "Industrials", "Building Products", 40, "US", "NYSE"),
    ("ABT", "Abbott Laboratories", "Healthcare", "Medical Devices", 220, "US", "NYSE"),
    ("ABBV", "AbbVie", "Healthcare", "Biotechnology", 350, "US", "NYSE"),
    ("ACN", "Accenture", "Technology", "IT Services", 250, "US", "NYSE"),
    ("ADBE", "Adobe Inc.", "Technology", "Software", 60, "US", "NASDAQ"),
    ("AMD", "Advanced Micro Devices", "Technology", "Semiconductors", 200, "US", "NASDAQ"),
    ("AES", "AES Corporation", "Utilities", "Power", 25, "US", "NYSE"),
    ("AFL", "Aflac", "Financials", "Insurance", 40, "US", "NYSE"),
    ("A", "Agilent Technologies", "Healthcare", "Life Sciences", 50, "US", "NYSE"),
    ("APD", "Air Products", "Materials", "Chemicals", 25, "US", "NYSE"),
    ("ABNB", "Airbnb", "Consumer Discretionary", "Hospitality", 40, "US", "NASDAQ"),
    ("AKAM", "Akamai Technologies", "Technology", "Internet Services", 60, "US", "NASDAQ"),
    ("ALB", "Albemarle Corporation", "Materials", "Chemicals", 25, "US", "NYSE"),
    ("ARE", "Alexandria Real Estate Equities", "Real Estate", "REITs", 25, "US", "NYSE"),
    ("ALGN", "Align Technology", "Healthcare", "Medical Devices", 50, "US", "NASDAQ"),
    ("ALLE", "Allegion", "Industrials", "Building Products", 40, "US", "NYSE"),
    ("LNT", "Alliant Energy", "Utilities", "Electric Utilities", 25, "US", "NYSE"),
    ("ALL", "Allstate", "Financials", "Insurance", 40, "US", "NYSE"),
    ("GOOGL", "Alphabet Inc. (Class A)", "Communication Services", "Media", 2200, "US", "NASDAQ"),
    ("GOOG", "Alphabet Inc. (Class C)", "Communication Services", "Media", 2200, "US", "NASDAQ"),
    ("MO", "Altria", "Consumer Staples", "Tobacco", 40, "US", "NYSE"),
    ("AMZN", "Amazon", "Consumer Discretionary", "Retail", 2100, "US", "NASDAQ"),
    ("AMCR", "Amcor", "Materials", "Packaging", 25, "US", "NYSE"),
    ("AEE", "Ameren", "Utilities", "Utilities", 25, "US", "NYSE"),
    ("AEP", "American Electric Power", "Utilities", "Electric Utilities", 25, "US", "NYSE"),
    ("AXP", "American Express", "Financials", "Consumer Finance", 180, "US", "NYSE"),
    ("AIG", "American International Group", "Financials", "Insurance", 40, "US", "NYSE"),
    ("AMT", "American Tower", "Real Estate", "REITs", 100, "US", "NYSE"),
    ("AWK", "American Water Works", "Utilities", "Water Utilities", 25, "US", "NYSE"),
    ("AMP", "Ameriprise Financial", "Financials", "Asset Management", 40, "US", "NYSE"),
    ("AME", "Ametek", "Industrials", "Electrical Equipment", 40, "US", "NYSE"),
    ("AMGN", "Amgen", "Healthcare", "Biotechnology", 50, "US", "NASDAQ"),
    ("APH", "Amphenol", "Technology", "Electronics", 60, "US", "NASDAQ"),
    ("ADI", "Analog Devices", "Technology", "Semiconductors", 60, "US", "NASDAQ"),
    ("AON", "Aon plc", "Financials", "Insurance", 40, "US", "NYSE"),
    ("APA", "APA Corporation", "Energy", "Oil & Gas", 35, "US", "NYSE"),
    ("APO", "Apollo Global Management", "Financials", "Asset Management", 40, "US", "NYSE"),
    ("AAPL", "Apple Inc.", "Technology", "Hardware", 3500, "US", "NASDAQ"),
    ("AMAT", "Applied Materials", "Technology", "Semiconductor Equipment", 60, "US", "NASDAQ"),
    ("APTV", "Aptiv", "Consumer Discretionary", "Automotive", 40, "US", "NYSE"),
    ("ACGL", "Arch Capital Group", "Financials", "Insurance", 40, "US", "NASDAQ"),
    ("ADM", "Archer Daniels Midland", "Consumer Staples", "Agriculture", 40, "US", "NYSE"),
    ("ANET", "Arista Networks", "Technology", "Networking", 60, "US", "NASDAQ"),
    ("AJG", "Arthur J. Gallagher & Co.", "Financials", "Insurance", 40, "US", "NYSE"),
    ("AIZ", "Assurant", "Financials", "Insurance", 40, "US", "NYSE"),
    ("T", "AT&T", "Communication Services", "Telecom", 50, "US", "NYSE"),
    ("ATO", "Atmos Energy", "Utilities", "Gas Utilities", 25, "US", "NYSE"),
    ("ADSK", "Autodesk", "Technology", "Software", 60, "US", "NASDAQ"),
    ("ADP", "Automatic Data Processing", "Industrials", "Business Services", 40, "US", "NYSE"),
    ("AZO", "AutoZone", "Consumer Discretionary", "Retail", 40, "US", "NASDAQ"),
    ("AVB", "AvalonBay Communities", "Real Estate", "REITs", 25, "US", "NYSE"),
    ("AVY", "Avery Dennison", "Materials", "Packaging", 25, "US", "NYSE"),
    ("AXON", "Axon Enterprise", "Industrials", "Aerospace", 40, "US", "NASDAQ"),
    ("BKR", "Baker Hughes", "Energy", "Oil & Gas Services", 35, "US", "NYSE"),
    ("BALL", "Ball Corporation", "Materials", "Packaging", 25, "US", "NYSE"),
    ("BAC", "Bank of America", "Financials", "Banks", 40, "US", "NYSE"),
    ("BAX", "Baxter International", "Healthcare", "Medical Devices", 50, "US", "NYSE"),
    ("BDX", "Becton Dickinson", "Healthcare", "Medical Devices", 50, "US", "NYSE"),
    ("BRK.B", "Berkshire Hathaway", "Financials", "Conglomerates", 1000, "US", "NYSE"),
    ("BBY", "Best Buy", "Consumer Discretionary", "Retail", 40, "US", "NASDAQ"),
    ("TECH", "Bio-Techne", "Healthcare", "Life Sciences", 50, "US", "NASDAQ"),
    ("BIIB", "Biogen", "Healthcare", "Biotechnology", 50, "US", "NASDAQ"),
    ("BLK", "BlackRock", "Financials", "Asset Management", 150, "US", "NYSE"),
    ("BX", "Blackstone Inc.", "Financials", "Asset Management", 40, "US", "NYSE"),
    ("XYZ", "Block Inc.", "Financials", "Fintech", 40, "US", "NASDAQ"),
    ("BK", "BNY Mellon", "Financials", "Asset Management", 40, "US", "NYSE"),
    ("BA", "Boeing", "Industrials", "Aerospace", 130, "US", "NYSE"),
    ("BKNG", "Booking Holdings", "Consumer Discretionary", "Hospitality", 40, "US", "NASDAQ"),
    ("BSX", "Boston Scientific", "Healthcare", "Medical Devices", 50, "US", "NYSE"),
    ("BMY", "Bristol Myers Squibb", "Healthcare", "Pharmaceuticals", 50, "US", "NYSE"),
    ("AVGO", "Broadcom", "Technology", "Semiconductors", 1000, "US", "NASDAQ"),
    ("BR", "Broadridge Financial Solutions", "Industrials", "Business Services", 40, "US", "NYSE"),
    ("BRO", "Brown & Brown", "Financials", "Insurance", 40, "US", "NYSE"),
    ("BF.B", "Brown-Forman", "Consumer Staples", "Beverages", 40, "US", "NYSE"),
    ("BLDR", "Builders FirstSource", "Industrials", "Building Products", 40, "US", "NYSE"),
    ("BG", "Bunge Global", "Consumer Staples", "Agriculture", 40, "US", "NYSE"),
    ("BXP", "BXP Inc.", "Real Estate", "REITs", 25, "US", "NYSE"),
    ("CHRW", "C.H. Robinson", "Industrials", "Transportation", 40, "US", "NYSE"),
    ("CDNS", "Cadence Design Systems", "Technology", "Software", 60, "US", "NASDAQ"),
    ("CZR", "Caesars Entertainment", "Consumer Discretionary", "Entertainment", 40, "US", "NYSE"),
    ("CPT", "Camden Property Trust", "Real Estate", "REITs", 25, "US", "NYSE"),
    ("CPB", "Campbell's Company", "Consumer Staples", "Food & Beverage", 40, "US", "NYSE"),
    ("COF", "Capital One", "Financials", "Consumer Finance", 40, "US", "NYSE"),
    ("CAH", "Cardinal Health", "Healthcare", "Health Services", 50, "US", "NYSE"),
    ("KMX", "CarMax", "Consumer Discretionary", "Retail", 40, "US", "NASDAQ"),
    ("CCL", "Carnival", "Consumer Discretionary", "Hospitality", 40, "US", "NYSE"),
    ("CARR", "Carrier Global", "Industrials", "Building Products", 40, "US", "NYSE"),
    ("CAT", "Caterpillar Inc.", "Industrials", "Machinery", 180, "US", "NYSE"),
    ("CBOE", "Cboe Global Markets", "Financials", "Financial Services", 40, "US", "NYSE"),
    ("CBRE", "CBRE Group", "Real Estate", "Real Estate Services", 25, "US", "NYSE"),
    ("CDW", "CDW Corporation", "Technology", "IT Services", 60, "US", "NASDAQ"),
    ("COR", "Cencora", "Healthcare", "Health Services", 50, "US", "NYSE"),
    ("CNC", "Centene Corporation", "Healthcare", "Health Insurance", 50, "US", "NYSE"),
    ("CNP", "CenterPoint Energy", "Utilities", "Utilities", 25, "US", "NYSE"),
    ("CF", "CF Industries", "Materials", "Chemicals", 25, "US", "NYSE"),
    ("CRL", "Charles River Laboratories", "Healthcare", "Life Sciences", 50, "US", "NYSE"),
    ("SCHW", "Charles Schwab Corporation", "Financials", "Investment Banking", 40, "US", "NYSE"),
    ("CHTR", "Charter Communications", "Communication Services", "Telecom", 50, "US", "NASDAQ"),
    ("CVX", "Chevron Corporation", "Energy", "Oil & Gas", 280, "US", "NYSE"),
    ("CMG", "Chipotle Mexican Grill", "Consumer Discretionary", "Restaurants", 40, "US", "NYSE"),
    ("CB", "Chubb Limited", "Financials", "Insurance", 40, "US", "NYSE"),
    ("CHD", "Church & Dwight", "Consumer Staples", "Household Products", 40, "US", "NYSE"),
    ("CI", "Cigna", "Healthcare", "Health Services", 50, "US", "NYSE"),
    ("CINF", "Cincinnati Financial", "Financials", "Insurance", 40, "US", "NYSE"),
    ("CTAS", "Cintas", "Industrials", "Business Services", 40, "US", "NYSE"),
    ("CSCO", "Cisco", "Technology", "Networking", 250, "US", "NASDAQ"),
    ("C", "Citigroup", "Financials", "Banks", 40, "US", "NYSE"),
    ("CFG", "Citizens Financial Group", "Financials", "Banks", 40, "US", "NYSE"),
    ("CLX", "Clorox", "Consumer Staples", "Household Products", 40, "US", "NYSE"),
    ("CME", "CME Group", "Financials", "Financial Services", 40, "US", "NYSE"),
    ("CMS", "CMS Energy", "Utilities", "Utilities", 25, "US", "NYSE"),
    ("KO", "Coca-Cola Company", "Consumer Staples", "Food & Beverage", 300, "US", "NYSE"),
    ("CTSH", "Cognizant", "Technology", "IT Services", 60, "US", "NASDAQ"),
    ("COIN", "Coinbase", "Financials", "Financial Services", 40, "US", "NASDAQ"),
    ("CL", "Colgate-Palmolive", "Consumer Staples", "Household Products", 40, "US", "NYSE"),
    ("CMCSA", "Comcast", "Communication Services", "Telecom", 50, "US", "NASDAQ"),
    ("CAG", "Conagra Brands", "Consumer Staples", "Food & Beverage", 40, "US", "NYSE"),
    ("COP", "ConocoPhillips", "Energy", "Oil & Gas", 35, "US", "NYSE"),
    ("ED", "Consolidated Edison", "Utilities", "Utilities", 25, "US", "NYSE"),
    ("STZ", "Constellation Brands", "Consumer Staples", "Beverages", 40, "US", "NYSE"),
    ("CEG", "Constellation Energy", "Utilities", "Electric Utilities", 25, "US", "NASDAQ"),
    ("COO", "Cooper Companies", "Healthcare", "Medical Devices", 50, "US", "NYSE"),
    ("CPRT", "Copart", "Industrials", "Business Services", 40, "US", "NASDAQ"),
    ("GLW", "Corning Inc.", "Technology", "Electronics", 60, "US", "NASDAQ"),
    ("CPAY", "Corpay", "Financials", "Fintech", 40, "US", "NASDAQ"),
    ("CTVA", "Corteva", "Materials", "Chemicals", 25, "US", "NASDAQ"),
    ("CSGP", "CoStar Group", "Real Estate", "Real Estate Services", 25, "US", "NASDAQ"),
    ("COST", "Costco", "Consumer Staples", "Retail", 400, "US", "NASDAQ"),
    ("CTRA", "Coterra", "Energy", "Oil & Gas", 35, "US", "NYSE"),
    ("CRWD", "CrowdStrike", "Technology", "Software", 60, "US", "NASDAQ"),
    ("CCI", "Crown Castle", "Real Estate", "REITs", 25, "US", "NYSE"),
    ("CSX", "CSX Corporation", "Industrials", "Transportation", 40, "US", "NYSE"),
    ("CMI", "Cummins", "Industrials", "Machinery", 40, "US", "NYSE"),
    ("CVS", "CVS Health", "Healthcare", "Health Services", 50, "US", "NYSE"),
    ("DHR", "Danaher Corporation", "Healthcare", "Life Sciences", 50, "US", "NYSE"),
    ("DRI", "Darden Restaurants", "Consumer Discretionary", "Restaurants", 40, "US", "NYSE"),
    ("DDOG", "Datadog", "Technology", "Software", 60, "US", "NASDAQ"),
    ("DVA", "DaVita", "Healthcare", "Health Services", 50, "US", "NYSE"),
    ("DAY", "Dayforce", "Industrials", "Business Services", 40, "US", "NYSE"),
    ("DECK", "Deckers Brands", "Consumer Discretionary", "Apparel", 40, "US", "NASDAQ"),
    ("DE", "Deere & Company", "Industrials", "Machinery", 40, "US", "NYSE"),
    ("DELL", "Dell Technologies", "Technology", "Hardware", 60, "US", "NASDAQ"),
    ("DAL", "Delta Air Lines", "Industrials", "Transportation", 40, "US", "NYSE"),
    ("DVN", "Devon Energy", "Energy", "Oil & Gas", 35, "US", "NYSE"),
    ("DXCM", "Dexcom", "Healthcare", "Medical Devices", 50, "US", "NASDAQ"),
    ("FANG", "Diamondback Energy", "Energy", "Oil & Gas", 35, "US", "NYSE"),
    ("DLR", "Digital Realty", "Real Estate", "REITs", 25, "US", "NYSE"),
    ("DG", "Dollar General", "Consumer Staples", "Retail", 40, "US", "NASDAQ"),
    ("DLTR", "Dollar Tree", "Consumer Staples", "Retail", 40, "US", "NASDAQ"),
    ("D", "Dominion Energy", "Utilities", "Utilities", 25, "US", "NYSE"),
    ("DPZ", "Domino's", "Consumer Discretionary", "Restaurants", 40, "US", "NYSE"),
    ("DASH", "DoorDash", "Consumer Discretionary", "Consumer Services", 40, "US", "NASDAQ"),
    ("DOV", "Dover Corporation", "Industrials", "Machinery", 40, "US", "NYSE"),
    ("DOW", "Dow Inc.", "Materials", "Chemicals", 25, "US", "NYSE"),
    ("DHI", "D.R. Horton", "Consumer Discretionary", "Construction", 40, "US", "NYSE"),
    ("DTE", "DTE Energy", "Utilities", "Utilities", 25, "US", "NYSE"),
    ("DUK", "Duke Energy", "Utilities", "Electric Utilities", 90, "US", "NYSE"),
    ("DD", "DuPont", "Materials", "Chemicals", 25, "US", "NYSE"),
    ("EMN", "Eastman Chemical Company", "Materials", "Chemicals", 25, "US", "NYSE"),
    ("ETN", "Eaton Corporation", "Industrials", "Electrical Equipment", 40, "US", "NYSE"),
    ("EBAY", "eBay Inc.", "Consumer Discretionary", "Retail", 40, "US", "NASDAQ"),
    ("ECL", "Ecolab", "Materials", "Chemicals", 25, "US", "NYSE"),
    ("EIX", "Edison International", "Utilities", "Electric Utilities", 25, "US", "NYSE"),
    ("EW", "Edwards Lifesciences", "Healthcare", "Medical Devices", 50, "US", "NYSE"),
    ("EA", "Electronic Arts", "Communication Services", "Entertainment", 50, "US", "NASDAQ"),
    ("ELV", "Elevance Health", "Healthcare", "Health Insurance", 50, "US", "NYSE"),
    ("EMR", "Emerson Electric", "Industrials", "Electrical Equipment", 40, "US", "NYSE"),
    ("ENPH", "Enphase Energy", "Technology", "Semiconductor Equipment", 60, "US", "NASDAQ"),
    ("ETR", "Entergy", "Utilities", "Electric Utilities", 25, "US", "NYSE"),
    ("EOG", "EOG Resources", "Energy", "Oil & Gas", 35, "US", "NYSE"),
    ("EPAM", "EPAM Systems", "Technology", "IT Services", 60, "US", "NASDAQ"),
    ("EQT", "EQT Corporation", "Energy", "Oil & Gas", 35, "US", "NYSE"),
    ("EFX", "Equifax", "Industrials", "Consulting", 40, "US", "NYSE"),
    ("EQIX", "Equinix", "Real Estate", "REITs", 25, "US", "NYSE"),
    ("EQR", "Equity Residential", "Real Estate", "REITs", 25, "US", "NYSE"),
    ("ERIE", "Erie Indemnity", "Financials", "Insurance", 40, "US", "NYSE"),
    ("ESS", "Essex Property Trust", "Real Estate", "REITs", 25, "US", "NYSE"),
    ("EL", "Estee Lauder Companies", "Consumer Staples", "Personal Care", 40, "US", "NYSE"),
    ("EG", "Everest Group", "Financials", "Insurance", 40, "US", "NYSE"),
    ("EVRG", "Evergy", "Utilities", "Electric Utilities", 25, "US", "NYSE"),
    ("ES", "Eversource Energy", "Utilities", "Electric Utilities", 25, "US", "NYSE"),
    ("EXC", "Exelon", "Utilities", "Electric Utilities", 25, "US", "NYSE"),
    ("EXE", "Expand Energy", "Energy", "Oil & Gas", 35, "US", "NYSE"),
    ("EXPE", "Expedia Group", "Consumer Discretionary", "Hospitality", 40, "US", "NYSE"),
    ("EXPD", "Expeditors International", "Industrials", "Transportation", 40, "US", "NYSE"),
    ("EXR", "Extra Space Storage", "Real Estate", "REITs", 25, "US", "NYSE"),
    ("XOM", "ExxonMobil", "Energy", "Oil & Gas", 500, "US", "NYSE"),
    ("FFIV", "F5 Inc.", "Technology", "Networking", 60, "US", "NASDAQ"),
    ("FDS", "FactSet", "Financials", "Financial Services", 40, "US", "NYSE"),
    ("FICO", "Fair Isaac", "Technology", "Software", 60, "US", "NASDAQ"),
    ("FAST", "Fastenal", "Industrials", "Distribution", 40, "US", "NASDAQ"),
    ("FRT", "Federal Realty Investment Trust", "Real Estate", "REITs", 25, "US", "NYSE"),
    ("FDX", "FedEx", "Industrials", "Transportation", 40, "US", "NYSE"),
    ("FIS", "Fidelity National Information Services", "Financials", "Fintech", 40, "US", "NYSE"),
    ("FITB", "Fifth Third Bancorp", "Financials", "Banks", 40, "US", "NYSE"),
    ("FSLR", "First Solar", "Technology", "Semiconductors", 60, "US", "NASDAQ"),
    ("FE", "FirstEnergy", "Utilities", "Electric Utilities", 25, "US", "NYSE"),
    ("FI", "Fiserv", "Financials", "Fintech", 40, "US", "NYSE"),
    ("F", "Ford Motor Company", "Consumer Discretionary", "Automotive", 40, "US", "NYSE"),
    ("FTNT", "Fortinet", "Technology", "Software", 60, "US", "NASDAQ"),
    ("FTV", "Fortive", "Industrials", "Machinery", 40, "US", "NYSE"),
    ("FOXA", "Fox Corporation (Class A)", "Communication Services", "Media", 50, "US", "NASDAQ"),
    ("FOX", "Fox Corporation (Class B)", "Communication Services", "Media", 50, "US", "NASDAQ"),
    ("BEN", "Franklin Resources", "Financials", "Asset Management", 40, "US", "NYSE"),
    ("FCX", "Freeport-McMoRan", "Materials", "Mining", 25, "US", "NYSE"),
    ("GRMN", "Garmin", "Consumer Discretionary", "Electronics", 40, "US", "NASDAQ"),
    ("IT", "Gartner", "Technology", "IT Services", 60, "US", "NYSE"),
    ("GE", "GE Aerospace", "Industrials", "Aerospace", 200, "US", "NYSE"),
    ("GEHC", "GE HealthCare", "Healthcare", "Medical Devices", 50, "US", "NASDAQ"),
    ("GEV", "GE Vernova", "Industrials", "Electrical Equipment", 40, "US", "NASDAQ"),
    ("GEN", "Gen Digital", "Technology", "Software", 60, "US", "NASDAQ"),
    ("GNRC", "Generac", "Industrials", "Electrical Equipment", 40, "US", "NASDAQ"),
    ("GD", "General Dynamics", "Industrials", "Aerospace", 40, "US", "NYSE"),
    ("GIS", "General Mills", "Consumer Staples", "Food & Beverage", 40, "US", "NYSE"),
    ("GM", "General Motors", "Consumer Discretionary", "Automotive", 40, "US", "NYSE"),
    ("GPC", "Genuine Parts Company", "Consumer Discretionary", "Distribution", 40, "US", "NYSE"),
    ("GILD", "Gilead Sciences", "Healthcare", "Biotechnology", 50, "US", "NASDAQ"),
    ("GPN", "Global Payments", "Financials", "Fintech", 40, "US", "NYSE"),
    ("GL", "Globe Life", "Financials", "Insurance", 40, "US", "NYSE"),
    ("GDDY", "GoDaddy", "Technology", "Internet Services", 60, "US", "NASDAQ"),
    ("GS", "Goldman Sachs", "Financials", "Investment Banking", 180, "US", "NYSE"),
    ("HAL", "Halliburton", "Energy", "Oil & Gas Services", 35, "US", "NYSE"),
    ("HIG", "Hartford Financial Services", "Financials", "Insurance", 40, "US", "NYSE"),
    ("HAS", "Hasbro", "Consumer Discretionary", "Consumer Products", 40, "US", "NYSE"),
    ("HCA", "HCA Healthcare", "Healthcare", "Health Services", 50, "US", "NYSE"),
    ("DOC", "Healthpeak Properties", "Real Estate", "REITs", 25, "US", "NYSE"),
    ("HSIC", "Henry Schein", "Healthcare", "Health Services", 50, "US", "NYSE"),
    ("HSY", "Hershey Company", "Consumer Staples", "Food & Beverage", 40, "US", "NYSE"),
    ("HPE", "Hewlett Packard Enterprise", "Technology", "Hardware", 60, "US", "NASDAQ"),
    ("HLT", "Hilton Worldwide", "Consumer Discretionary", "Hospitality", 40, "US", "NYSE"),
    ("HOLX", "Hologic", "Healthcare", "Medical Devices", 50, "US", "NASDAQ"),
    ("HD", "Home Depot", "Consumer Discretionary", "Retail", 400, "US", "NYSE"),
    ("HON", "Honeywell", "Industrials", "Conglomerates", 40, "US", "NYSE"),
    ("HRL", "Hormel Foods", "Consumer Staples", "Food & Beverage", 40, "US", "NYSE"),
    ("HST", "Host Hotels & Resorts", "Real Estate", "REITs", 25, "US", "NYSE"),
    ("HWM", "Howmet Aerospace", "Industrials", "Aerospace", 40, "US", "NYSE"),
    ("HPQ", "HP Inc.", "Technology", "Hardware", 60, "US", "NYSE"),
    ("HUBB", "Hubbell Incorporated", "Industrials", "Machinery", 40, "US", "NYSE"),
    ("HUM", "Humana", "Healthcare", "Health Insurance", 50, "US", "NYSE"),
    ("HBAN", "Huntington Bancshares", "Financials", "Banks", 40, "US", "NYSE"),
    ("HII", "Huntington Ingalls Industries", "Industrials", "Aerospace", 40, "US", "NYSE"),
    ("IBM", "IBM", "Technology", "IT Services", 200, "US", "NYSE"),
    ("IEX", "IDEX Corporation", "Industrials", "Machinery", 40, "US", "NYSE"),
    ("IDXX", "Idexx Laboratories", "Healthcare", "Medical Devices", 50, "US", "NASDAQ"),
    ("ITW", "Illinois Tool Works", "Industrials", "Machinery", 40, "US", "NYSE"),
    ("INCY", "Incyte", "Healthcare", "Biotechnology", 50, "US", "NYSE"),
    ("IR", "Ingersoll Rand", "Industrials", "Machinery", 40, "US", "NYSE"),
    ("PODD", "Insulet Corporation", "Healthcare", "Medical Devices", 50, "US", "NASDAQ"),
    ("INTC", "Intel", "Technology", "Semiconductors", 60, "US", "NASDAQ"),
    ("ICE", "Intercontinental Exchange", "Financials", "Financial Services", 40, "US", "NYSE"),
    ("IFF", "International Flavors & Fragrances", "Materials", "Chemicals", 25, "US", "NYSE"),
    ("IP", "International Paper", "Materials", "Packaging", 25, "US", "NYSE"),
    ("IPG", "Interpublic Group", "Communication Services", "Advertising", 50, "US", "NYSE"),
    ("INTU", "Intuit", "Technology", "Software", 200, "US", "NASDAQ"),
    ("ISRG", "Intuitive Surgical", "Healthcare", "Medical Devices", 50, "US", "NASDAQ"),
    ("IVZ", "Invesco", "Financials", "Asset Management", 40, "US", "NYSE"),
    ("INVH", "Invitation Homes", "Real Estate", "REITs", 25, "US", "NYSE"),
    ("IQV", "IQVIA", "Healthcare", "Life Sciences", 50, "US", "NYSE"),
    ("IRM", "Iron Mountain", "Real Estate", "REITs", 25, "US", "NYSE"),
    ("JBHT", "J.B. Hunt", "Industrials", "Transportation", 40, "US", "NYSE"),
    ("JBL", "Jabil", "Technology", "Electronics", 60, "US", "NASDAQ"),
    ("JKHY", "Jack Henry & Associates", "Financials", "Fintech", 40, "US", "NASDAQ"),
    ("J", "Jacobs Solutions", "Industrials", "Construction", 40, "US", "NYSE"),
    ("JNJ", "Johnson & Johnson", "Healthcare", "Pharmaceuticals", 400, "US", "NYSE"),
    ("JCI", "Johnson Controls", "Industrials", "Building Products", 40, "US", "NYSE"),
    ("JPM", "JPMorgan Chase", "Financials", "Banks", 700, "US", "NYSE"),
    ("K", "Kellanova", "Consumer Staples", "Food & Beverage", 40, "US", "NYSE"),
    ("KVUE", "Kenvue", "Consumer Staples", "Personal Care", 40, "US", "NYSE"),
    ("KDP", "Keurig Dr Pepper", "Consumer Staples", "Food & Beverage", 40, "US", "NASDAQ"),
    ("KEY", "KeyCorp", "Financials", "Banks", 40, "US", "NYSE"),
    ("KEYS", "Keysight Technologies", "Technology", "Electronics", 60, "US", "NASDAQ"),
    ("KMB", "Kimberly-Clark", "Consumer Staples", "Household Products", 40, "US", "NYSE"),
    ("KIM", "Kimco Realty", "Real Estate", "REITs", 25, "US", "NYSE"),
    ("KMI", "Kinder Morgan", "Energy", "Oil & Gas", 35, "US", "NYSE"),
    ("KKR", "KKR & Co.", "Financials", "Asset Management", 40, "US", "NYSE"),
    ("KLAC", "KLA Corporation", "Technology", "Semiconductor Equipment", 60, "US", "NASDAQ"),
    ("KHC", "Kraft Heinz", "Consumer Staples", "Food & Beverage", 40, "US", "NASDAQ"),
    ("KR", "Kroger", "Consumer Staples", "Retail", 40, "US", "NYSE"),
    ("LHX", "L3Harris", "Industrials", "Aerospace", 40, "US", "NYSE"),
    ("LH", "Labcorp", "Healthcare", "Health Services", 50, "US", "NYSE"),
    ("LRCX", "Lam Research", "Technology", "Semiconductor Equipment", 60, "US", "NASDAQ"),
    ("LW", "Lamb Weston", "Consumer Staples", "Food & Beverage", 40, "US", "NYSE"),
    ("LVS", "Las Vegas Sands", "Consumer Discretionary", "Entertainment", 40, "US", "NYSE"),
    ("LDOS", "Leidos", "Industrials", "Business Services", 40, "US", "NYSE"),
    ("LEN", "Lennar", "Consumer Discretionary", "Construction", 40, "US", "NYSE"),
    ("LII", "Lennox International", "Industrials", "Building Products", 40, "US", "NYSE"),
    ("LLY", "Eli Lilly", "Healthcare", "Pharmaceuticals", 800, "US", "NYSE"),
    ("LIN", "Linde plc", "Materials", "Chemicals", 250, "US", "NYSE"),
    ("LYV", "Live Nation Entertainment", "Communication Services", "Entertainment", 50, "US", "NYSE"),
    ("LKQ", "LKQ Corporation", "Consumer Discretionary", "Distribution", 40, "US", "NYSE"),
    ("LMT", "Lockheed Martin", "Industrials", "Aerospace", 40, "US", "NYSE"),
    ("L", "Loews Corporation", "Financials", "Insurance", 40, "US", "NYSE"),
    ("LOW", "Lowe's", "Consumer Discretionary", "Retail", 40, "US", "NYSE"),
    ("LULU", "Lululemon Athletica", "Consumer Discretionary", "Apparel", 40, "US", "NASDAQ"),
    ("LYB", "LyondellBasell", "Materials", "Chemicals", 25, "US", "NYSE"),
    ("MTB", "M&T Bank", "Financials", "Banks", 40, "US", "NYSE"),
    ("MPC", "Marathon Petroleum", "Energy", "Oil & Gas", 35, "US", "NYSE"),
    ("MKTX", "MarketAxess", "Financials", "Financial Services", 40, "US", "NASDAQ"),
    ("MAR", "Marriott International", "Consumer Discretionary", "Hospitality", 40, "US", "NASDAQ"),
    ("MMC", "Marsh McLennan", "Financials", "Insurance", 40, "US", "NYSE"),
    ("MLM", "Martin Marietta Materials", "Materials", "Building Materials", 25, "US", "NYSE"),
    ("MAS", "Masco", "Industrials", "Building Products", 40, "US", "NYSE"),
    ("MA", "Mastercard", "Financials", "Fintech", 500, "US", "NYSE"),
    ("MTCH", "Match Group", "Communication Services", "Media", 50, "US", "NYSE"),
    ("MKC", "McCormick & Company", "Consumer Staples", "Food & Beverage", 40, "US", "NYSE"),
    ("MCD", "McDonald's", "Consumer Discretionary", "Restaurants", 40, "US", "NYSE"),
    ("MCK", "McKesson Corporation", "Healthcare", "Health Services", 50, "US", "NYSE"),
    ("MDT", "Medtronic", "Healthcare", "Medical Devices", 50, "US", "NYSE"),
    ("MRK", "Merck & Co.", "Healthcare", "Pharmaceuticals", 300, "US", "NYSE"),
    ("META", "Meta Platforms", "Communication Services", "Media", 1700, "US", "NASDAQ"),
    ("MET", "MetLife", "Financials", "Insurance", 40, "US", "NYSE"),
    ("MTD", "Mettler Toledo", "Healthcare", "Life Sciences", 50, "US", "NYSE"),
    ("MGM", "MGM Resorts", "Consumer Discretionary", "Entertainment", 40, "US", "NYSE"),
    ("MCHP", "Microchip Technology", "Technology", "Semiconductors", 60, "US", "NASDAQ"),
    ("MU", "Micron Technology", "Technology", "Semiconductors", 60, "US", "NASDAQ"),
    ("MSFT", "Microsoft", "Technology", "Software", 3200, "US", "NASDAQ"),
    ("MAA", "Mid-America Apartment Communities", "Real Estate", "REITs", 25, "US", "NYSE"),
    ("MRNA", "Moderna", "Healthcare", "Biotechnology", 50, "US", "NASDAQ"),
    ("MHK", "Mohawk Industries", "Consumer Discretionary", "Home Furnishings", 40, "US", "NYSE"),
    ("MOH", "Molina Healthcare", "Healthcare", "Health Insurance", 50, "US", "NYSE"),
    ("TAP", "Molson Coors Beverage Company", "Consumer Staples", "Beverages", 40, "US", "NYSE"),
    ("MDLZ", "Mondelez International", "Consumer Staples", "Food & Beverage", 40, "US", "NASDAQ"),
    ("MPWR", "Monolithic Power Systems", "Technology", "Semiconductors", 60, "US", "NASDAQ"),
    ("MNST", "Monster Beverage", "Consumer Staples", "Food & Beverage", 40, "US", "NASDAQ"),
    ("MCO", "Moody's Corporation", "Financials", "Financial Services", 40, "US", "NYSE"),
    ("MS", "Morgan Stanley", "Financials", "Investment Banking", 40, "US", "NYSE"),
    ("MOS", "Mosaic Company", "Materials", "Chemicals", 25, "US", "NYSE"),
    ("MSI", "Motorola Solutions", "Technology", "Networking", 60, "US", "NYSE"),
    ("MSCI", "MSCI Inc.", "Financials", "Financial Services", 40, "US", "NYSE"),
    ("NDAQ", "Nasdaq Inc.", "Financials", "Financial Services", 40, "US", "NYSE"),
    ("NTAP", "NetApp", "Technology", "Hardware", 60, "US", "NASDAQ"),
    ("NFLX", "Netflix", "Communication Services", "Entertainment", 350, "US", "NASDAQ"),
    ("NEM", "Newmont", "Materials", "Mining", 25, "US", "NYSE"),
    ("NWSA", "News Corp (Class A)", "Communication Services", "Media", 50, "US", "NYSE"),
    ("NWS", "News Corp (Class B)", "Communication Services", "Media", 50, "US", "NYSE"),
    ("NEE", "NextEra Energy", "Utilities", "Utilities", 160, "US", "NYSE"),
    ("NKE", "Nike Inc.", "Consumer Discretionary", "Apparel", 40, "US", "NYSE"),
    ("NI", "NiSource", "Utilities", "Utilities", 25, "US", "NYSE"),
    ("NDSN", "Nordson Corporation", "Industrials", "Machinery", 40, "US", "NASDAQ"),
    ("NSC", "Norfolk Southern", "Industrials", "Transportation", 40, "US", "NYSE"),
    ("NTRS", "Northern Trust", "Financials", "Asset Management", 40, "US", "NYSE"),
    ("NOC", "Northrop Grumman", "Industrials", "Aerospace", 40, "US", "NYSE"),
    ("NCLH", "Norwegian Cruise Line Holdings", "Consumer Discretionary", "Hospitality", 40, "US", "NASDAQ"),
    ("NRG", "NRG Energy", "Utilities", "Power", 25, "US", "NYSE"),
    ("NUE", "Nucor", "Materials", "Metals", 25, "US", "NYSE"),
    ("NVDA", "Nvidia", "Technology", "Semiconductors", 3000, "US", "NASDAQ"),
    ("NVR", "NVR Inc.", "Consumer Discretionary", "Construction", 40, "US", "NYSE"),
    ("NXPI", "NXP Semiconductors", "Technology", "Semiconductors", 60, "US", "NASDAQ"),
    ("ORLY", "O'Reilly Automotive", "Consumer Discretionary", "Retail", 40, "US", "NASDAQ"),
    ("OXY", "Occidental Petroleum", "Energy", "Oil & Gas", 35, "US", "NYSE"),
    ("ODFL", "Old Dominion", "Industrials", "Transportation", 40, "US", "NASDAQ"),
    ("OMC", "Omnicom Group", "Communication Services", "Advertising", 50, "US", "NYSE"),
    ("ON", "ON Semiconductor", "Technology", "Semiconductors", 60, "US", "NASDAQ"),
    ("OKE", "Oneok", "Energy", "Oil & Gas", 35, "US", "NYSE"),
    ("ORCL", "Oracle Corporation", "Technology", "Software", 350, "US", "NASDAQ"),
    ("OTIS", "Otis Worldwide", "Industrials", "Machinery", 40, "US", "NYSE"),
    ("PCAR", "Paccar", "Industrials", "Machinery", 40, "US", "NASDAQ"),
    ("PKG", "Packaging Corporation of America", "Materials", "Packaging", 25, "US", "NYSE"),
    ("PLTR", "Palantir Technologies", "Technology", "Software", 60, "US", "NASDAQ"),
    ("PANW", "Palo Alto Networks", "Technology", "Software", 60, "US", "NASDAQ"),
    ("PSKY", "Paramount Skydance Corporation", "Communication Services", "Entertainment", 50, "US", "NYSE"),
    ("PH", "Parker Hannifin", "Industrials", "Machinery", 40, "US", "NYSE"),
    ("PAYX", "Paychex", "Industrials", "Business Services", 40, "US", "NASDAQ"),
    ("PAYC", "Paycom", "Industrials", "Business Services", 40, "US", "NASDAQ"),
    ("PYPL", "PayPal", "Financials", "Fintech", 40, "US", "NASDAQ"),
    ("PNR", "Pentair", "Industrials", "Machinery", 40, "US", "NYSE"),
    ("PEP", "PepsiCo", "Consumer Staples", "Food & Beverage", 250, "US", "NASDAQ"),
    ("PFE", "Pfizer", "Healthcare", "Pharmaceuticals", 50, "US", "NYSE"),
    ("PCG", "PG&E Corporation", "Utilities", "Utilities", 25, "US", "NYSE"),
    ("PM", "Philip Morris International", "Consumer Staples", "Tobacco", 40, "US", "NYSE"),
    ("PSX", "Phillips 66", "Energy", "Oil & Gas", 35, "US", "NYSE"),
    ("PNW", "Pinnacle West Capital", "Utilities", "Utilities", 25, "US", "NYSE"),
    ("PNC", "PNC Financial Services", "Financials", "Banks", 40, "US", "NYSE"),
    ("POOL", "Pool Corporation", "Consumer Discretionary", "Distribution", 40, "US", "NASDAQ"),
    ("PPG", "PPG Industries", "Materials", "Chemicals", 25, "US", "NYSE"),
    ("PPL", "PPL Corporation", "Utilities", "Electric Utilities", 25, "US", "NYSE"),
    ("PFG", "Principal Financial Group", "Financials", "Insurance", 40, "US", "NYSE"),
    ("PG", "Procter & Gamble", "Consumer Staples", "Personal Care", 400, "US", "NYSE"),
    ("PGR", "Progressive Corporation", "Financials", "Insurance", 40, "US", "NYSE"),
    ("PLD", "Prologis", "Real Estate", "REITs", 120, "US", "NYSE"),
    ("PRU", "Prudential Financial", "Financials", "Insurance", 40, "US", "NYSE"),
    ("PEG", "Public Service Enterprise Group", "Utilities", "Electric Utilities", 25, "US", "NYSE"),
    ("PTC", "PTC Inc.", "Technology", "Software", 60, "US", "NYSE"),
    ("PSA", "Public Storage", "Real Estate", "REITs", 25, "US", "NYSE"),
    ("PHM", "PulteGroup", "Consumer Discretionary", "Construction", 40, "US", "NYSE"),
    ("PWR", "Quanta Services", "Industrials", "Construction", 40, "US", "NYSE"),
    ("QCOM", "Qualcomm", "Technology", "Semiconductors", 200, "US", "NASDAQ"),
    ("DGX", "Quest Diagnostics", "Healthcare", "Health Services", 50, "US", "NYSE"),
    ("RL", "Ralph Lauren Corporation", "Consumer Discretionary", "Apparel", 40, "US", "NYSE"),
    ("RJF", "Raymond James Financial", "Financials", "Investment Banking", 40, "US", "NYSE"),
    ("RTX", "RTX Corporation", "Industrials", "Aerospace", 40, "US", "NYSE"),
    ("O", "Realty Income", "Real Estate", "REITs", 25, "US", "NYSE"),
    ("REG", "Regency Centers", "Real Estate", "REITs", 25, "US", "NYSE"),
    ("REGN", "Regeneron Pharmaceuticals", "Healthcare", "Biotechnology", 50, "US", "NASDAQ"),
    ("RF", "Regions Financial Corporation", "Financials", "Banks", 40, "US", "NYSE"),
    ("RSG", "Republic Services", "Industrials", "Environmental Services", 40, "US", "NYSE"),
    ("RMD", "ResMed", "Healthcare", "Medical Devices", 50, "US", "NYSE"),
    ("RVTY", "Revvity", "Healthcare", "Medical Devices", 50, "US", "NYSE"),
    ("ROK", "Rockwell Automation", "Industrials", "Electrical Equipment", 40, "US", "NYSE"),
    ("ROL", "Rollins Inc.", "Industrials", "Environmental Services", 40, "US", "NYSE"),
    ("ROP", "Roper Technologies", "Technology", "Electronics", 60, "US", "NASDAQ"),
    ("ROST", "Ross Stores", "Consumer Discretionary", "Retail", 40, "US", "NASDAQ"),
    ("RCL", "Royal Caribbean Group", "Consumer Discretionary", "Hospitality", 40, "US", "NYSE"),
    ("SPGI", "S&P Global", "Financials", "Financial Services", 40, "US", "NYSE"),
    ("CRM", "Salesforce", "Technology", "Software", 300, "US", "NASDAQ"),
    ("SBAC", "SBA Communications", "Real Estate", "REITs", 25, "US", "NYSE"),
    ("SLB", "Schlumberger", "Energy", "Oil & Gas Services", 35, "US", "NYSE"),
    ("STX", "Seagate Technology", "Technology", "Hardware", 60, "US", "NASDAQ"),
    ("SRE", "Sempra", "Utilities", "Utilities", 25, "US", "NYSE"),
    ("NOW", "ServiceNow", "Technology", "Software", 200, "US", "NASDAQ"),
    ("SHW", "Sherwin-Williams", "Materials", "Chemicals", 25, "US", "NYSE"),
    ("SPG", "Simon Property Group", "Real Estate", "REITs", 25, "US", "NYSE"),
    ("SWKS", "Skyworks Solutions", "Technology", "Semiconductors", 60, "US", "NASDAQ"),
    ("SJM", "J.M. Smucker Company", "Consumer Staples", "Food & Beverage", 40, "US", "NYSE"),
    ("SW", "Smurfit Westrock", "Materials", "Packaging", 25, "US", "NYSE"),
    ("SNA", "Snap-on", "Industrials", "Machinery", 40, "US", "NYSE"),
    ("SOLV", "Solventum", "Healthcare", "Health Tech", 50, "US", "NASDAQ"),
    ("SO", "Southern Company", "Utilities", "Electric Utilities", 25, "US", "NYSE"),
    ("LUV", "Southwest Airlines", "Industrials", "Transportation", 40, "US", "NYSE"),
    ("SWK", "Stanley Black & Decker", "Industrials", "Machinery", 40, "US", "NYSE"),
    ("SBUX", "Starbucks", "Consumer Discretionary", "Restaurants", 40, "US", "NASDAQ"),
    ("STT", "State Street Corporation", "Financials", "Asset Management", 40, "US", "NYSE"),
    ("STLD", "Steel Dynamics", "Materials", "Metals", 25, "US", "NYSE"),
    ("STE", "Steris", "Healthcare", "Medical Devices", 50, "US", "NYSE"),
    ("SYK", "Stryker Corporation", "Healthcare", "Medical Devices", 50, "US", "NYSE"),
    ("SMCI", "Supermicro", "Technology", "Hardware", 60, "US", "NASDAQ"),
    ("SYF", "Synchrony Financial", "Financials", "Consumer Finance", 40, "US", "NYSE"),
    ("SNPS", "Synopsys", "Technology", "Software", 60, "US", "NASDAQ"),
    ("SYY", "Sysco", "Consumer Staples", "Food Distribution", 40, "US", "NYSE"),
    ("TMUS", "T-Mobile US", "Communication Services", "Telecom", 50, "US", "NASDAQ"),
    ("TROW", "T. Rowe Price", "Financials", "Asset Management", 40, "US", "NASDAQ"),
    ("TTWO", "Take-Two Interactive", "Communication Services", "Entertainment", 50, "US", "NASDAQ"),
    ("TPR", "Tapestry Inc.", "Consumer Discretionary", "Apparel", 40, "US", "NYSE"),
    ("TRGP", "Targa Resources", "Energy", "Oil & Gas", 35, "US", "NYSE"),
    ("TGT", "Target Corporation", "Consumer Staples", "Retail", 40, "US", "NYSE"),
    ("TEL", "TE Connectivity", "Technology", "Electronics", 60, "US", "NASDAQ"),
    ("TDY", "Teledyne Technologies", "Technology", "Electronics", 60, "US", "NASDAQ"),
    ("TER", "Teradyne", "Technology", "Semiconductor Equipment", 60, "US", "NASDAQ"),
    ("TSLA", "Tesla Inc.", "Consumer Discretionary", "Automotive", 1200, "US", "NASDAQ"),
    ("TXN", "Texas Instruments", "Technology", "Semiconductors", 190, "US", "NASDAQ"),
    ("TPL", "Texas Pacific Land Corporation", "Energy", "Oil & Gas", 35, "US", "NASDAQ"),
    ("TXT", "Textron", "Industrials", "Aerospace", 40, "US", "NYSE"),
    ("TMO", "Thermo Fisher Scientific", "Healthcare", "Life Sciences", 250, "US", "NYSE"),
    ("TJX", "TJX Companies", "Consumer Discretionary", "Retail", 40, "US", "NYSE"),
    ("TKO", "TKO Group Holdings", "Communication Services", "Entertainment", 50, "US", "NYSE"),
    ("TTD", "Trade Desk", "Communication Services", "Advertising", 50, "US", "NASDAQ"),
    ("TSCO", "Tractor Supply", "Consumer Discretionary", "Retail", 40, "US", "NASDAQ"),
    ("TT", "Trane Technologies", "Industrials", "Building Products", 40, "US", "NYSE"),
    ("TDG", "TransDigm Group", "Industrials", "Aerospace", 40, "US", "NYSE"),
    ("TRV", "Travelers Companies", "Financials", "Insurance", 40, "US", "NYSE"),
    ("TRMB", "Trimble Inc.", "Technology", "Electronics", 60, "US", "NASDAQ"),
    ("TFC", "Truist Financial", "Financials", "Banks", 40, "US", "NYSE"),
    ("TYL", "Tyler Technologies", "Technology", "Software", 60, "US", "NASDAQ"),
    ("TSN", "Tyson Foods", "Consumer Staples", "Food & Beverage", 40, "US", "NYSE"),
    ("USB", "U.S. Bancorp", "Financials", "Banks", 40, "US", "NYSE"),
    ("UBER", "Uber", "Industrials", "Transportation", 40, "US", "NYSE"),
    ("UDR", "UDR Inc.", "Real Estate", "REITs", 25, "US", "NYSE"),
    ("ULTA", "Ulta Beauty", "Consumer Discretionary", "Retail", 40, "US", "NASDAQ"),
    ("UNP", "Union Pacific Corporation", "Industrials", "Transportation", 40, "US", "NYSE"),
    ("UAL", "United Airlines Holdings", "Industrials", "Transportation", 40, "US", "NYSE"),
    ("UPS", "United Parcel Service", "Industrials", "Transportation", 40, "US", "NYSE"),
    ("URI", "United Rentals", "Industrials", "Distribution", 40, "US", "NYSE"),
    ("UNH", "UnitedHealth Group", "Healthcare", "Health Insurance", 500, "US", "NYSE"),
    ("UHS", "Universal Health Services", "Healthcare", "Health Services", 50, "US", "NYSE"),
    ("VLO", "Valero Energy", "Energy", "Oil & Gas", 35, "US", "NYSE"),
    ("VTR", "Ventas", "Real Estate", "REITs", 25, "US", "NYSE"),
    ("VLTO", "Veralto", "Industrials", "Environmental Services", 40, "US", "NYSE"),
    ("VRSN", "Verisign", "Technology", "Internet Services", 60, "US", "NYSE"),
    ("VRSK", "Verisk Analytics", "Industrials", "Consulting", 40, "US", "NYSE"),
    ("VZ", "Verizon", "Communication Services", "Telecom", 50, "US", "NYSE"),
    ("VRTX", "Vertex Pharmaceuticals", "Healthcare", "Biotechnology", 50, "US", "NASDAQ"),
    ("VTRS", "Viatris", "Healthcare", "Pharmaceuticals", 50, "US", "NASDAQ"),
    ("VICI", "Vici Properties", "Real Estate", "REITs", 25, "US", "NYSE"),
    ("V", "Visa Inc.", "Financials", "Fintech", 600, "US", "NYSE"),
    ("VST", "Vistra Corp.", "Utilities", "Electric Utilities", 25, "US", "NYSE"),
    ("VMC", "Vulcan Materials Company", "Materials", "Building Materials", 25, "US", "NYSE"),
    ("WRB", "W.R. Berkley Corporation", "Financials", "Insurance", 40, "US", "NYSE"),
    ("GWW", "W.W. Grainger", "Industrials", "Machinery", 40, "US", "NYSE"),
    ("WAB", "Wabtec", "Industrials", "Machinery", 40, "US", "NYSE"),
    ("WBA", "Walgreens Boots Alliance", "Consumer Staples", "Retail", 40, "US", "NASDAQ"),
    ("WMT", "Walmart", "Consumer Staples", "Retail", 700, "US", "NYSE"),
    ("DIS", "Walt Disney Company", "Communication Services", "Entertainment", 50, "US", "NYSE"),
    ("WBD", "Warner Bros. Discovery", "Communication Services", "Media", 50, "US", "NYSE"),
    ("WM", "Waste Management", "Industrials", "Environmental Services", 40, "US", "NYSE"),
    ("WAT", "Waters Corporation", "Healthcare", "Life Sciences", 50, "US", "NYSE"),
    ("WEC", "WEC Energy Group", "Utilities", "Electric Utilities", 25, "US", "NYSE"),
    ("WFC", "Wells Fargo", "Financials", "Banks", 40, "US", "NYSE"),
    ("WELL", "Welltower", "Real Estate", "REITs", 25, "US", "NYSE"),
    ("WST", "West Pharmaceutical Services", "Healthcare", "Medical Devices", 50, "US", "NYSE"),
    ("WDC", "Western Digital", "Technology", "Hardware", 60, "US", "NASDAQ"),
    ("WY", "Weyerhaeuser", "Real Estate", "REITs", 25, "US", "NYSE"),
    ("WSM", "Williams-Sonoma Inc.", "Consumer Discretionary", "Retail", 40, "US", "NYSE"),
    ("WMB", "Williams Companies", "Energy", "Oil & Gas", 35, "US", "NYSE"),
    ("WTW", "Willis Towers Watson", "Financials", "Insurance", 40, "US", "NYSE"),
    ("WDAY", "Workday Inc.", "Technology", "Software", 60, "US", "NASDAQ"),
    ("WYNN", "Wynn Resorts", "Consumer Discretionary", "Entertainment", 40, "US", "NASDAQ"),
    ("XEL", "Xcel Energy", "Utilities", "Utilities", 25, "US", "NYSE"),
    ("XYL", "Xylem Inc.", "Industrials", "Machinery", 40, "US", "NYSE"),
    ("YUM", "Yum! Brands", "Consumer Discretionary", "Restaurants", 40, "US", "NYSE"),
    ("ZBRA", "Zebra Technologies", "Technology", "Electronics", 60, "US", "NASDAQ"),
    ("ZBH", "Zimmer Biomet", "Healthcare", "Medical Devices", 50, "US", "NYSE"),
    ("ZTS", "Zoetis", "Healthcare", "Pharmaceuticals", 50, "US", "NYSE"),
]


SAMPLE_ADDRESSES = [
    "123 Main Street", "456 Corporate Blvd", "789 Innovation Way",
    "1000 Technology Drive", "555 Market Street", "200 Park Avenue",
    "300 Industrial Parkway", "One Commerce Square", "1500 Broadway",
    "800 Fifth Avenue",
]
SAMPLE_CITIES = [
    "New York", "San Francisco", "Chicago", "Boston", "Seattle",
    "Austin", "Atlanta", "Denver", "Los Angeles", "Dallas",
    "Philadelphia", "San Jose", "Charlotte", "Minneapolis", "Houston",
]
SAMPLE_ZIPS = [
    "10001", "94105", "60601", "02101", "98101",
    "78701", "30301", "80201", "90001", "75201",
    "19101", "95101", "28201", "55401", "77001",
]
SAMPLE_AREA_CODES = [
    "212", "415", "312", "617", "206",
    "512", "404", "303", "213", "214",
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
        city = random.choice(SAMPLE_CITIES)
        city_idx = SAMPLE_CITIES.index(city)
        area_code = SAMPLE_AREA_CODES[city_idx % len(SAMPLE_AREA_CODES)]
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
            "address": random.choice(SAMPLE_ADDRESSES),
            "city": city,
            "phone": f"({area_code}) {random.randint(200, 999)}-{random.randint(1000, 9999)}",
            "zip": SAMPLE_ZIPS[city_idx % len(SAMPLE_ZIPS)],
            "long_business_summary": f"{name} is a leading {industry.lower()} company in the {sector.lower()} sector.",
            "full_time_employees": random.randint(500, 300000),
            "web_site": f"https://www.{name.lower().split()[0].replace('.', '').replace(',', '')}.com",
            "report_date": "2025-01-31",
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


PEOPLE_FIELDS = [
    "person_id", "name", "title", "organization", "type", "tickers",
    "age", "born", "pay", "exercised", "unexercised",
]


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
        age = random.randint(40, 68)
        rows.append({
            "person_id": f"PER-{pid:03d}",
            "name": name,
            "title": random.choice(TITLES_EXEC),
            "organization": random.choice(ORGS_EXEC),
            "type": "executive",
            "tickers": ";".join(covered),
            "age": age,
            "born": 2025 - age,
            "pay": random.randint(200000, 5000000) if random.random() > 0.3 else "",
            "exercised": random.randint(0, 1000000) if random.random() > 0.5 else 0,
            "unexercised": random.randint(0, 500000) if random.random() > 0.5 else 0,
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
            "age": "",
            "born": "",
            "pay": "",
            "exercised": "",
            "unexercised": "",
        })
        pid += 1
    path = STRUCTURED_DIR / "people.csv"
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=PEOPLE_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    print(f"  Created {path} ({len(rows)} rows)")


# --------------- datasets.csv ---------------

def generate_datasets():
    rows = [
        {"dataset_id": "DS-001", "name": "stocks", "display_name": "Stock Universe", "description": "Core stock universe with fundamentals", "record_count": 503, "id_field": "ticker", "category": "market_data"},
        {"dataset_id": "DS-002", "name": "people", "display_name": "People Directory", "description": "Executives and analysts", "record_count": 40, "id_field": "person_id", "category": "contacts"},
        {"dataset_id": "DS-003", "name": "sectors", "display_name": "Sector Reference", "description": "Sector and industry taxonomy", "record_count": 10, "id_field": "sector", "category": "reference"},
        {"dataset_id": "DS-004", "name": "watchlists", "display_name": "Watchlists", "description": "Portfolio manager watchlists", "record_count": 0, "id_field": "watchlist_id", "category": "portfolio"},
        {"dataset_id": "DS-005", "name": "meetings", "display_name": "Meeting Notes", "description": "Research meeting records", "record_count": 0, "id_field": "meeting_id", "category": "research"},
        {"dataset_id": "DS-006", "name": "ratings", "display_name": "Analyst Ratings", "description": "Internal analyst ratings and targets", "record_count": 0, "id_field": "rating_id", "category": "research"},
        {"dataset_id": "DS-007", "name": "portfolios", "display_name": "Portfolios", "description": "Portfolio holdings and allocations", "record_count": 0, "id_field": "portfolio_id", "category": "portfolio"},
        {"dataset_id": "DS-008", "name": "events", "display_name": "Corporate Events", "description": "Earnings calls, conferences, filings", "record_count": 0, "id_field": "event_id", "category": "market_data"},
        {"dataset_id": "DS-009", "name": "macro", "display_name": "Macro Indicators", "description": "Macroeconomic data points", "record_count": 0, "id_field": "indicator_id", "category": "market_data"},
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


def generate_notes():
    """Generate sample analyst notes as placeholder PDFs."""
    files = []
    notes = [
        ("GOOGL_Q4_2024_earnings_preview.pdf", "GOOGL", "Alphabet Inc. (Class A)",
         "Q4 2024 Earnings Preview", "2025-01-08",
         "Alphabet Inc. Q4 2024 earnings preview notes"),
        ("GOOGL_Q4_2024_earnings_recap.pdf", "GOOGL", "Alphabet Inc. (Class A)",
         "Q4 2024 Earnings Recap", "2025-01-29",
         "Alphabet Inc. Q4 2024 post-earnings recap notes"),
    ]
    for i, (filename, ticker, company, title, date, desc) in enumerate(notes, 1):
        path = UNSTRUCTURED_DIR / "notes" / filename
        content = f"[PDF Placeholder] {title}: {company} ({ticker}) - {date}\n"
        path.write_text(content)
        files.append({
            "file_id": f"FILE-{500 + i:03d}",
            "filename": filename,
            "path": f"notes/{filename}",
            "type": "notes",
            "mime_type": "application/pdf",
            "size_bytes": len(content.encode()),
            "tickers": [ticker],
            "date": date,
            "description": desc,
        })
    print(f"  Created {len(files)} notes")
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
    all_files.extend(generate_notes())
    generate_manifest(all_files)

    print("\nDone! All sample data generated.")


if __name__ == "__main__":
    main()
