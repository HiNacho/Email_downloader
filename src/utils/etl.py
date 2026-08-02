#!/usr/bin/env python3
"""
Stock Price ETL Pipeline
========================
Extracts daily stock price listings from Nigerian Exchange PDFs.
Supports parsing in-memory raw PDF bytes directly into an SQLite database,
avoiding any local file writes.
"""

import os
import re
import io
import sqlite3
import logging
from datetime import datetime
from pypdf import PdfReader

DB_FILE = os.path.join('data', 'processed', 'stocks.db')

def init_db():
    """
    Initialize SQLite database and schema.
    """
    # Ensure data directory exists
    os.makedirs(os.path.dirname(DB_FILE), exist_ok=True)
    
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    
    # Create metadata table for processed price list files
    c.execute('''
        CREATE TABLE IF NOT EXISTS price_lists (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT UNIQUE,
            report_date TEXT,
            processed_at TEXT
        )
    ''')
    
    # Create individual stock prices table
    c.execute('''
        CREATE TABLE IF NOT EXISTS stock_prices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            price_list_id INTEGER,
            report_date TEXT,
            symbol TEXT,
            p_close REAL,
            open REAL,
            high REAL,
            low REAL,
            close REAL,
            change REAL,
            pct_change REAL,
            deals INTEGER,
            volume INTEGER,
            value REAL,
            vwap REAL,
            FOREIGN KEY(price_list_id) REFERENCES price_lists(id)
        )
    ''')
    conn.commit()
    conn.close()

def parse_pdf_date(filename):
    """
    Extract report date (YYYY-MM-DD) from price list filenames.
    Supports NGS/MorganCapital standard formats.
    """
    fn = filename.lower()
    
    # Style 1: pricelist_mkt_summary_d_all_YYYY_MM_DD_...
    m = re.search(r'pricelist_mkt_summary_d_all_(\d{4})_(\d{2})_(\d{2})', fn)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
        
    # Style 2: month_day_year (e.g. jan_12_2026, july_31st_2026, june_04_2026)
    m2 = re.search(r'([a-z]+)[_-](\d{1,2})(?:st|nd|rd|th)?[_-](\d{4})', fn)
    if m2:
        mon_str = m2.group(1)
        day_str = m2.group(2)
        year_str = m2.group(3)
        
        month_map = {
            'jan': '01', 'feb': '02', 'mar': '03', 'apr': '04', 'may': '05', 'jun': '06',
            'jul': '07', 'aug': '08', 'sep': '09', 'oct': '10', 'nov': '11', 'dec': '12',
            'january': '01', 'february': '02', 'march': '03', 'april': '04', 'june': '06',
            'july': '07', 'august': '08', 'september': '09', 'october': '10', 'november': '11', 'december': '12'
        }
        mon_num = month_map.get(mon_str)
        if mon_num:
            return f"{year_str}-{mon_num}-{int(day_str):02d}"
            
    # Fallback to file modification date or current date
    try:
        stat = os.stat(os.path.join('data', 'raw', filename))
        return datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d")
    except Exception:
        return datetime.now().strftime("%Y-%m-%d")

def parse_and_load_in_memory(filename, pdf_bytes):
    """
    Parse a PDF from an in-memory byte stream and insert its stock records into the database.
    Returns the number of parsed stock records loaded.
    """
    init_db()
    
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    
    # Check if this file has already been processed
    c.execute("SELECT id FROM price_lists WHERE filename = ?", (filename,))
    if c.fetchone():
        logging.info(f"ETL: File '{filename}' has already been processed. Skipping.")
        conn.close()
        return 0
        
    report_date = parse_pdf_date(filename)
    logging.info(f"ETL: Parsing '{filename}' ({report_date}) directly in-memory...")
    
    try:
        # Wrap bytes stream in BytesIO for PdfReader
        pdf_file = io.BytesIO(pdf_bytes)
        reader = PdfReader(pdf_file)
        
        full_text = ""
        for page in reader.pages:
            text_content = page.extract_text()
            if text_content:
                full_text += text_content + "\n"
                
        lines = full_text.split('\n')
        parsed_stocks = []
        row_pattern = re.compile(r'^(\d+)([A-Z0-9\-\_]+)\s+(.+)$')
        
        for line in lines:
            line = line.strip()
            match = row_pattern.match(line)
            if match:
                sn = match.group(1)
                symbol = match.group(2)
                rest = match.group(3)
                
                tokens = rest.split()
                if len(tokens) == 11:
                    p_close, open_val, high, low, close, change, pct_change, deals, volume, value, vwap = tokens
                elif len(tokens) == 9:
                    p_close, open_val, high, low, close, deals, volume, value, vwap = tokens
                    change = "0.00"
                    pct_change = "0.00"
                else:
                    continue
                    
                try:
                    parsed_stocks.append((
                        symbol,
                        float(p_close.replace(',', '')),
                        float(open_val.replace(',', '')),
                        float(high.replace(',', '')),
                        float(low.replace(',', '')),
                        float(close.replace(',', '')),
                        float(change.replace(',', '')),
                        float(pct_change.replace(',', '')),
                        int(deals.replace(',', '')),
                        int(volume.replace(',', '')),
                        float(value.replace(',', '')),
                        float(vwap.replace(',', ''))
                    ))
                except ValueError:
                    continue
                    
        if parsed_stocks:
            processed_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            c.execute(
                "INSERT INTO price_lists (filename, report_date, processed_at) VALUES (?, ?, ?)",
                (filename, report_date, processed_at)
            )
            price_list_id = c.lastrowid
            
            insert_rows = []
            for s in parsed_stocks:
                insert_rows.append((
                    price_list_id, report_date, s[0], s[1], s[2], s[3], s[4], s[5], s[6], s[7], s[8], s[9], s[10], s[11]
                ))
                
            c.executemany('''
                INSERT INTO stock_prices (
                    price_list_id, report_date, symbol, p_close, open, high, low, close, change, pct_change, deals, volume, value, vwap
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', insert_rows)
            
            conn.commit()
            logging.info(f"ETL: Loaded {len(parsed_stocks)} records from in-memory PDF: '{filename}'.")
            conn.close()
            return len(parsed_stocks)
        else:
            logging.warning(f"ETL: Found no valid stock records in PDF bytes for '{filename}'.")
            
    except Exception as e:
        logging.error(f"ETL: In-memory parsing error for '{filename}': {e}")
        
    conn.close()
    return 0

def seed_mock_data():
    """
    Seed mock data to stocks.db for demonstration purposes in Mock mode.
    """
    init_db()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    
    # Check if already seeded
    c.execute("SELECT id FROM price_lists WHERE filename = 'DAILY_PRICE_LIST_AUG_02.pdf'")
    if c.fetchone():
        conn.close()
        return
        
    mock_dates = ['2026-08-02', '2026-08-01', '2026-07-31']
    mock_symbols = ['MTNN', 'ACCESSCORP', 'ARADEL', 'BUACEMENT', 'DANGSUGAR', 'FCMB', 'ZENITHBANK']
    
    base_prices = {
        'MTNN': 200.0,
        'ACCESSCORP': 23.0,
        'ARADEL': 725.0,
        'BUACEMENT': 183.0,
        'DANGSUGAR': 71.0,
        'FCMB': 11.2,
        'ZENITHBANK': 38.5
    }
    
    import random
    random.seed(42) # Deterministic values
    
    for date_str in mock_dates:
        filename = f"DAILY_PRICE_LIST_{date_str.replace('-', '_')}.pdf"
        if date_str == '2026-08-01':
            filename = "DAILY_PRICE_LIST_ATTACHMENT_AUG_01.xlsx"
            
        processed_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        c.execute("INSERT OR IGNORE INTO price_lists (filename, report_date, processed_at) VALUES (?, ?, ?)",
                  (filename, date_str, processed_at))
        c.execute("SELECT id FROM price_lists WHERE filename = ?", (filename,))
        price_list_id = c.fetchone()[0]
        
        rows = []
        for symbol in mock_symbols:
            base = base_prices[symbol]
            change = round(random.uniform(-3.0, 3.0), 2) if symbol != 'ACCESSCORP' else round(random.uniform(-0.3, 0.3), 2)
            close = round(base + change, 2)
            pct_change = round((change / base) * 100, 2)
            p_close = base
            open_val = round(p_close + random.uniform(-0.1, 0.1), 2)
            high = max(open_val, close) + round(random.uniform(0, 0.3), 2)
            low = min(open_val, close) - round(random.uniform(0, 0.3), 2)
            deals = random.randint(30, 800)
            volume = random.randint(5000, 500000)
            value = round(volume * close, 2)
            vwap = round((open_val + high + low + close) / 4, 2)
            
            rows.append((
                price_list_id, date_str, symbol, p_close, open_val, high, low, close, change, pct_change, deals, volume, value, vwap
            ))
            
        c.executemany('''
            INSERT INTO stock_prices (
                price_list_id, report_date, symbol, p_close, open, high, low, close, change, pct_change, deals, volume, value, vwap
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', rows)
        
    conn.commit()
    conn.close()
    logging.info("ETL: Seeded mock database data successfully.")

def run_etl(save_dir=os.path.join('data', 'raw')):
    """
    Scans save_dir for PDF files, reads them into memory, and loads them.
    (Left as a fallback tool in case PDFs are placed manually in the directory).
    """
    init_db()
    
    if not os.path.exists(save_dir):
        return 0
        
    files = [
        f for f in os.listdir(save_dir) 
        if f.lower().endswith('.pdf') 
        and not f.startswith('DAILY_PRICE_LIST_AUG') 
        and not f.startswith('DAILY_PRICE_LIST_JUL')
    ]
    
    loaded_count = 0
    for filename in files:
        pdf_path = os.path.join(save_dir, filename)
        try:
            with open(pdf_path, 'rb') as f:
                pdf_bytes = f.read()
            if parse_and_load_in_memory(filename, pdf_bytes) > 0:
                loaded_count += 1
        except Exception as e:
            logging.error(f"ETL: Failed to load local file '{filename}': {e}")
            
    return loaded_count

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
    run_etl()
