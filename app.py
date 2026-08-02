#!/usr/bin/env python3
"""
Email Downloader Web Dashboard Server
======================================
Serves a beautiful Web UI to configure and interact with the email downloader.
Uses built-in Python http.server for a zero-dependency setup.
"""

import os
import sys
import json
import time
import sqlite3
import logging
import threading
import webbrowser
import urllib.parse
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer

# Import core logic and ETL
import email_automate
import etl

PORT = 8080
is_sync_running = False
stop_requested = False

# Ensure WebUILogHandler is added to the root logger
root_logger = logging.getLogger()
root_logger.setLevel(logging.INFO)
if not any(isinstance(h, email_automate.WebUILogHandler) for h in root_logger.handlers):
    root_logger.addHandler(email_automate.web_ui_log_handler)

# Initialize database on startup
etl.init_db()

def run_sync_worker(params):
    """
    Background worker thread running the downloader logic.
    """
    global is_sync_running, stop_requested
    is_sync_running = True
    stop_requested = False
    
    try:
        logging.info("Starting sync run requested from Web UI...")
        
        save_dir = email_automate.DOWNLOAD_DIR
        email_automate.ensure_dir(save_dir)
        
        keyword = params.get('keyword', email_automate.SUBJECT_KEYWORD)
        unread_only = params.get('unreadOnly', False)
        start_date = params.get('startDate') or None
        end_date = params.get('endDate') or None
        force_mock = params.get('forceMock', False)
        
        # Decide if we run mock mode
        use_mock = force_mock
        if not use_mock and not os.path.exists(email_automate.CREDS_PATH):
            logging.warning(f"'{email_automate.CREDS_PATH}' not found in the current directory.")
            logging.warning("Falling back to Mock/Demo Mode. To connect to a real Gmail account, please provide client_secret.json.")
            use_mock = True
            
        if use_mock:
            logging.info("Running in Mock/Demo Mode...")
            if start_date or end_date:
                logging.info(f"Mock Date Range Filter: {start_date or 'ANY'} to {end_date or 'ANY'}")
                
            # Mock data representation
            mock_emails = [
                {"id": "mock_msg_001", "subject": "DAILY PRICE LIST - AUGUST 02, 2026", "date": "2026-08-02", "file": "DAILY_PRICE_LIST_AUG_02.pdf", "type": "link", "link": "https://morgancapitalgroup.com/downloads/DAILY_PRICE_LIST_AUG_02.pdf"},
                {"id": "mock_msg_002", "subject": "Daily Price Update August 01", "date": "2026-08-01", "file": "DAILY_PRICE_LIST_ATTACHMENT_AUG_01.xlsx", "type": "attachment"},
                {"id": "mock_msg_003", "subject": "DAILY PRICE LIST - JULY 31, 2026", "date": "2026-07-31", "file": "DAILY_PRICE_LIST_JUL_31.pdf", "type": "link", "link": "https://morgancapitalgroup.com/downloads/DAILY_PRICE_LIST_JUL_31.pdf"}
            ]
            
            # Filter mock emails by date range
            filtered_emails = []
            for email in mock_emails:
                email_date = datetime.strptime(email["date"], "%Y-%m-%d")
                if start_date:
                    sd = datetime.strptime(start_date, "%Y-%m-%d")
                    if email_date < sd:
                        continue
                if end_date:
                    ed = datetime.strptime(end_date, "%Y-%m-%d")
                    if email_date > ed:
                        continue
                filtered_emails.append(email)
                
            logging.info(f"Scanned emails. Matched: {len(filtered_emails)} emails.")
            
            for email in filtered_emails:
                if stop_requested:
                    logging.warning("Sync stopped by user.")
                    break
                    
                logging.info(f"Processing email ID: {email['id']}")
                
                # Simulate light network delay
                time.sleep(1.2)
                
                if email["type"] == "link":
                    logging.info(f"Found links in '{email['subject']}': ['{email['link']}']")
                    logging.info(f"Downloaded PDF from link (in-memory): {email['file']}")
                else:
                    logging.info(f"Downloaded attachment (in-memory): {email['file']}")
            
            # Seed mock SQLite database data at the end of mock sync
            etl.seed_mock_data()
        else:
            if not email_automate.GMAIL_API_AVAILABLE:
                logging.error("Google Client API modules are not available. Cannot connect to Gmail.")
                return
                
            logging.info("Authenticating with Gmail API...")
            service = email_automate.authenticate_gmail()
            logging.info("Searching for matching emails...")
            msg_ids = email_automate.search_emails(
                service, query_text=keyword, unread_only=unread_only,
                start_date=start_date, end_date=end_date
            )
            
            total_records = 0
            for msg_id in msg_ids:
                if stop_requested:
                    logging.warning("Sync stopped by user.")
                    break
                logging.info(f"Processing email ID: {msg_id}")
                records = email_automate.process_email(service, msg_id, save_dir)
                total_records += records
            logging.info(f"ETL: Successfully parsed and loaded {total_records} stock records directly to database.")
                
        if not stop_requested:
            logging.info("Sync completed successfully.")
            
    except Exception as e:
        logging.error(f"Error occurred during background sync: {e}")
    finally:
        is_sync_running = False

class WebUIRequestHandler(BaseHTTPRequestHandler):
    """
    Lightweight HTTP server serving index.html and handling JSON APIs.
    """
    def log_message(self, format, *args):
        # Suppress logging internal HTTP requests to stdout
        pass

    def do_GET(self):
        global is_sync_running
        parsed_path = urllib.parse.urlparse(self.path)
        
        if parsed_path.path == '/':
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.end_headers()
            with open('index.html', 'r', encoding='utf-8') as f:
                self.wfile.write(f.read().encode('utf-8'))
                
        elif parsed_path.path == '/api/status':
            creds_exist = os.path.exists(email_automate.CREDS_PATH)
            token_exist = os.path.exists(email_automate.TOKEN_PATH)
            
            # Retrieve and clear new logs from WebUILogHandler
            new_logs = list(email_automate.web_ui_log_handler.logs)
            email_automate.web_ui_log_handler.logs.clear()
            
            response_data = {
                "creds_exist": creds_exist,
                "token_exist": token_exist,
                "state": "running" if is_sync_running else "idle",
                "logs": new_logs
            }
            
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(response_data).encode('utf-8'))
            
        elif parsed_path.path == '/api/stocks':
            # Retrieve distinct symbols from SQLite
            symbols = []
            try:
                conn = sqlite3.connect(etl.DB_FILE)
                c = conn.cursor()
                c.execute("SELECT DISTINCT symbol FROM stock_prices ORDER BY symbol")
                symbols = [row[0] for row in c.fetchall()]
                conn.close()
            except Exception as e:
                logging.error(f"Failed to fetch stocks from DB: {e}")
                
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(symbols).encode('utf-8'))
            
        elif parsed_path.path == '/api/query':
            # Extract query parameters
            query_params = urllib.parse.parse_qs(parsed_path.query)
            symbol = query_params.get('symbol', [''])[0]
            start_date = query_params.get('startDate', [''])[0]
            end_date = query_params.get('endDate', [''])[0]
            
            results = []
            try:
                conn = sqlite3.connect(etl.DB_FILE)
                c = conn.cursor()
                
                sql = "SELECT report_date, symbol, p_close, open, high, low, close, change, pct_change, deals, volume, value, vwap FROM stock_prices WHERE 1=1"
                sql_params = []
                
                if symbol:
                    sql += " AND symbol = ?"
                    sql_params.append(symbol)
                if start_date:
                    sql += " AND report_date >= ?"
                    sql_params.append(start_date)
                if end_date:
                    sql += " AND report_date <= ?"
                    sql_params.append(end_date)
                    
                sql += " ORDER BY report_date DESC"
                
                c.execute(sql, sql_params)
                rows = c.fetchall()
                conn.close()
                
                for r in rows:
                    results.append({
                        "date": r[0],
                        "symbol": r[1],
                        "p_close": r[2],
                        "open": r[3],
                        "high": r[4],
                        "low": r[5],
                        "close": r[6],
                        "change": r[7],
                        "pct_change": r[8],
                        "deals": r[9],
                        "volume": r[10],
                        "value": r[11],
                        "vwap": r[12]
                    })
            except Exception as e:
                logging.error(f"Failed to query database: {e}")
                
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(results).encode('utf-8'))
            
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        global is_sync_running, stop_requested
        parsed_path = urllib.parse.urlparse(self.path)
        
        if parsed_path.path == '/api/run':
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            params = json.loads(post_data.decode('utf-8'))
            
            if is_sync_running:
                self.send_response(400)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({"status": "error", "message": "Downloader already running"}).encode('utf-8'))
                return
                
            # Start sync task in a background daemon thread
            t = threading.Thread(target=run_sync_worker, args=(params,), daemon=True)
            t.start()
            
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"status": "started"}).encode('utf-8'))
            
        elif parsed_path.path == '/api/stop':
            if is_sync_running:
                stop_requested = True
                logging.info("Downloader sync stop requested by user.")
                
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"status": "stop_requested"}).encode('utf-8'))
            
        elif parsed_path.path == '/api/etl/trigger':
            # Manually trigger ETL run
            try:
                loaded = etl.run_etl(email_automate.DOWNLOAD_DIR)
                # Seed mock data if no actual PDFs loaded, just to have data
                if loaded == 0 and not os.path.exists(email_automate.CREDS_PATH):
                    etl.seed_mock_data()
                    loaded = "mock data seeded"
                    
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({"status": "completed", "processed": loaded}).encode('utf-8'))
            except Exception as e:
                logging.error(f"Manual ETL failed: {e}")
                self.send_response(500)
                self.end_headers()
        else:
            self.send_response(404)
            self.end_headers()

def open_browser():
    """
    Slightly delayed browser launch to ensure the server is listening.
    """
    time.sleep(1.2)
    logging.info(f"Opening dashboard in your web browser: http://localhost:{PORT}")
    webbrowser.open(f"http://localhost:{PORT}")

def main():
    # Setup server-side terminal logging output
    log_formatter = logging.Formatter("%(asctime)s %(levelname)s: %(message)s")
    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(log_formatter)
    
    # Configure handlers on the root logger
    if not root_logger.handlers:
        root_logger.addHandler(sh)
        root_logger.addHandler(email_automate.web_ui_log_handler)
    else:
        # Avoid duplication
        if not any(isinstance(h, logging.StreamHandler) for h in root_logger.handlers):
            root_logger.addHandler(sh)
            
    server_address = ('', PORT)
    httpd = HTTPServer(server_address, WebUIRequestHandler)
    
    logging.info(f"Web Dashboard server starting on port {PORT}...")
    
    # Launch browser in a separate thread
    browser_thread = threading.Thread(target=open_browser, daemon=True)
    browser_thread.start()
    
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        logging.info("Shutting down Web Dashboard server...")
        httpd.server_close()

if __name__ == '__main__':
    main()
