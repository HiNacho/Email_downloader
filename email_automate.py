#!/usr/bin/env python3
"""
Gmail Daily Price List Automation Script
=======================================
Downloads daily price list files (PDF, XLSX, XLS, CSV) from Gmail.
Supports downloading actual attachments and extracting/downloading files from body links.
Includes a mock/demo mode if API credentials are not yet set up.
"""

import os
import re
import sys
import pickle
import logging
import base64
import requests
import argparse
from datetime import datetime
from urllib.parse import urlparse
import mimetypes

# Optional imports for Gmail API
try:
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import Request
    GMAIL_API_AVAILABLE = True
except ImportError:
    GMAIL_API_AVAILABLE = False

try:
    from tenacity import retry, stop_after_attempt, wait_exponential
except ImportError:
    # Basic fallback decorator if tenacity is not installed
    def retry(*args, **kwargs):
        def decorator(f):
            return f
        return decorator

# ---------------- Constants ----------------
SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']
TOKEN_PATH = 'token.pickle'
CREDS_PATH = 'client_secret.json'
DOWNLOAD_DIR = 'daily_price_lists'
LOG_FILE = 'download_log.txt'
SUBJECT_KEYWORD = "DAILY PRICE LIST"

# ---------------- Helper Functions ----------------
def ensure_dir(path):
    if not os.path.exists(path):
        os.makedirs(path)

def clean_filename(name):
    """
    Remove characters that might be problematic in filenames.
    """
    return "".join(c if c.isalnum() or c in "._-" else "_" for c in name)

def is_duplicate(filename):
    return os.path.exists(os.path.join(DOWNLOAD_DIR, filename))

# ---------------- Link Extraction & Downloading ----------------
def extract_links_from_body(body):
    """
    Extract HTTP/HTTPS links from the email body text.
    """
    url_pattern = r"https?://[^\s\)>\"]+"
    try:
        return re.findall(url_pattern, body)
    except Exception:
        # Fallback to simple matching if complex pattern fails
        return re.findall(r"https?://[^\s]+", body)

# Known domains that never contain PDF price lists (social media, newsletter tracking)
BLACKLISTED_DOMAINS = {
    'twitter.com', 'facebook.com', 'instagram.com', 'linkedin.com', 'youtube.com',
    'whatsapp.com', 'wa.link', 'mailchimp.com', 'list-manage.com', 'w3.org'
}

BLACKLISTED_EXTENSIONS = {
    '.png', '.jpg', '.jpeg', '.gif', '.svg', '.ico', '.css', '.js', '.woff', '.woff2'
}

def download_file_from_link(url):
    """
    Download a file from a direct link in-memory.
    Returns raw bytes of the file, or None if failed.
    """
    try:
        parsed = urlparse(url)
        netloc = parsed.netloc.lower()
        path = parsed.path.lower()
        
        # 1. Skip Google Drive
        if 'drive.google.com' in netloc:
            logging.warning(f"Google Drive link requires manual access: {url}")
            return None
            
        # 2. Skip blacklisted domains
        if any(domain in netloc for domain in BLACKLISTED_DOMAINS):
            return None
            
        # 3. Skip blacklisted extensions
        if any(path.endswith(ext) for ext in BLACKLISTED_EXTENSIONS):
            return None
            
        # 4. Use fast HTTP HEAD request (timeout=5s) to check Content-Type
        try:
            head_resp = requests.head(url, timeout=5, allow_redirects=True)
            content_type = head_resp.headers.get('content-type', '').lower()
        except Exception:
            head_resp = None
            content_type = ''
            
        # Skip if it is clearly not a PDF
        if head_resp is not None and 'application/pdf' not in content_type:
            return None
            
        # 5. Fetch the actual content
        resp = requests.get(url, timeout=10, allow_redirects=True)
        if resp.status_code == 200:
            content_type = resp.headers.get('content-type', '').lower()
            if 'application/pdf' in content_type:
                return resp.content
        else:
            logging.warning(f"Failed to download {url}: Status {resp.status_code}")
    except Exception as e:
        logging.debug(f"Error checking/downloading {url}: {e}")
    return None

# ---------------- Attachment Processing ----------------
def download_attachment(service, msg_id, part):
    """
    Download a single attachment from an email part in-memory.
    Returns raw decoded bytes, or None if failed.
    """
    try:
        att_id = part['body']['attachmentId']
        att = service.users().messages().attachments().get(
            userId='me', messageId=msg_id, id=att_id
        ).execute()
        
        data = att['data']
        file_data = base64.urlsafe_b64decode(data.encode('UTF-8'))
        return file_data
    except Exception as e:
        logging.error(f"Failed to download attachment: {e}")
        return None

# ---------------- Gmail Authentication ----------------
def authenticate_gmail():
    """
    Authenticate to Gmail API and return service object.
    Stores and reuses token for future runs.
    """
    if not os.path.exists(CREDS_PATH):
        raise FileNotFoundError(f"Missing '{CREDS_PATH}'. Please set up Google API credentials.")
        
    creds = None
    if os.path.exists(TOKEN_PATH):
        with open(TOKEN_PATH, 'rb') as token:
            creds = pickle.load(token)
            
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(CREDS_PATH, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(TOKEN_PATH, 'wb') as token:
            pickle.dump(creds, token)
            
    return build('gmail', 'v1', credentials=creds)

# ---------------- Web UI Log Handler ----------------
class WebUILogHandler(logging.Handler):
    def __init__(self):
        super().__init__()
        self.logs = []
        
    def emit(self, record):
        try:
            log_entry = self.format(record)
            self.logs.append(log_entry)
            # Cap at 1000 logs to avoid unbounded growth
            if len(self.logs) > 1000:
                self.logs.pop(0)
        except Exception:
            self.handleError(record)

# Global instance for app.py to poll
web_ui_log_handler = WebUILogHandler()
web_ui_log_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s: %(message)s"))

# ---------------- Email Search & Details ----------------
def search_emails(service, query_text=SUBJECT_KEYWORD, unread_only=False, start_date=None, end_date=None):
    """
    Search Gmail inbox for emails containing query_text in subject.
    Optionally filter by unread emails and date range.
    """
    search_query = f"subject:({query_text})"
    if unread_only:
        search_query += " is:unread"
        
    if start_date:
        search_query += f" after:{start_date.replace('-', '/')}"
    if end_date:
        try:
            from datetime import timedelta
            dt = datetime.strptime(end_date, "%Y-%m-%d")
            exclusive_end = (dt + timedelta(days=1)).strftime("%Y/%m/%d")
            search_query += f" before:{exclusive_end}"
        except Exception:
            search_query += f" before:{end_date.replace('-', '/')}"

    matched_ids = []
    page_token = None
    try:
        while True:
            response = service.users().messages().list(
                userId='me',
                q=search_query,
                pageToken=page_token,
                maxResults=100
            ).execute()
            messages = response.get('messages', [])
            for msg in messages:
                matched_ids.append(msg['id'])
            page_token = response.get('nextPageToken')
            if not page_token:
                break
        logging.info(f"Scanned emails. Matched: {len(matched_ids)}.")
        return matched_ids
    except HttpError as error:
        logging.error(f"An error occurred during email search: {error}")
        return []

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=2, min=2, max=10))
def get_email_details(service, msg_id):
    return service.users().messages().get(userId='me', id=msg_id, format='full').execute()

def process_email(service, msg_id, save_dir=None):
    """
    Process a single email: extract attachments and links in-memory and write them straight to the SQLite DB.
    Returns count of parsed records loaded.
    """
    msg = get_email_details(service, msg_id)
    if not msg:
        return 0
        
    total_loaded_records = 0
    payload = msg.get('payload', {})
    headers = payload.get('headers', [])
    subject = next((h['value'] for h in headers if h['name'] == 'Subject'), 'No Subject')
    
    # Try to determine a clean base filename from subject
    safe_subject = clean_filename(subject)
    
    # Extract parts
    parts = []
    if 'parts' in payload:
        parts = payload['parts']
    elif 'body' in payload and payload['body'].get('attachmentId'):
        parts = [payload]
        
    # Walk tree of parts to download attachments
    queue = list(parts)
    while queue:
        part = queue.pop(0)
        if 'parts' in part:
            queue.extend(part['parts'])
        filename = part.get('filename')
        if filename and part.get('body', {}).get('attachmentId'):
            ext = os.path.splitext(filename)[1].lower()
            if ext == '.pdf':
                pdf_bytes = download_attachment(service, msg_id, part)
                if pdf_bytes:
                    import etl
                    loaded = etl.parse_and_load_in_memory(filename, pdf_bytes)
                    total_loaded_records += loaded
                    
    # Walk tree to find body text
    body_parts = []
    queue = list(parts)
    if not parts and 'data' in payload.get('body', {}):
        body_parts.append(base64.urlsafe_b64decode(payload['body']['data']).decode('utf-8', errors='ignore'))
    else:
        while queue:
            part = queue.pop(0)
            if 'parts' in part:
                queue.extend(part['parts'])
            mime_type = part.get('mimeType', '')
            if mime_type.startswith('text/') and 'data' in part.get('body', {}):
                body_parts.append(base64.urlsafe_b64decode(part['body']['data']).decode('utf-8', errors='ignore'))
                
    body = '\n'.join(body_parts)
    if body:
        links = extract_links_from_body(body)
        if links:
            unique_links = list(set(links))
            logging.info(f"Found {len(unique_links)} unique links in '{subject}'. Checking/processing concurrently...")
            
            # We will download the links concurrently and parse/load them in-memory
            import concurrent.futures
            
            def task_download_and_load(url):
                pdf_bytes = download_file_from_link(url)
                if pdf_bytes:
                    parsed_url = urlparse(url)
                    fname = os.path.basename(parsed_url.path)
                    if not fname or not fname.lower().endswith('.pdf'):
                        fname = f"{safe_subject}.pdf"
                    else:
                        fname = clean_filename(fname)
                        
                    import etl
                    return etl.parse_and_load_in_memory(fname, pdf_bytes)
                return 0
                
            with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
                futures = {executor.submit(task_download_and_load, url): url for url in unique_links}
                for future in concurrent.futures.as_completed(futures):
                    total_loaded_records += future.result()
                    
    return total_loaded_records

# ---------------- Mock/Demo Mode ----------------
def run_mock_mode(save_dir, start_date=None, end_date=None):
    """
    Simulates the email scanning and file download behavior.
    Used for testing or demonstration. Supports date filtering.
    """
    logging.info("Starting in Mock/Demo Mode (simulating Gmail API sync)...")
    if start_date or end_date:
        logging.info(f"Mock Date Range Filter: {start_date or 'ANY'} to {end_date or 'ANY'}")
    ensure_dir(save_dir)
    
    mock_emails = [
        {"id": "mock_msg_001", "subject": "DAILY PRICE LIST - AUGUST 02, 2026", "date": "2026-08-02", "file": "DAILY_PRICE_LIST_AUG_02.pdf", "type": "link", "link": "https://morgancapitalgroup.com/downloads/DAILY_PRICE_LIST_AUG_02.pdf"},
        {"id": "mock_msg_002", "subject": "Daily Price Update August 01", "date": "2026-08-01", "file": "DAILY_PRICE_LIST_ATTACHMENT_AUG_01.xlsx", "type": "attachment"},
        {"id": "mock_msg_003", "subject": "DAILY PRICE LIST - JULY 31, 2026", "date": "2026-07-31", "file": "DAILY_PRICE_LIST_JUL_31.pdf", "type": "link", "link": "https://morgancapitalgroup.com/downloads/DAILY_PRICE_LIST_JUL_31.pdf"}
    ]
    
    # Filter mock emails by range
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
        
    downloaded_files = []
    logging.info(f"Scanned emails. Matched: {len(filtered_emails)} emails.")
    
    for email in filtered_emails:
        logging.info(f"Processing email ID: {email['id']}")
        file_path = os.path.join(save_dir, email["file"])
        
        if email["type"] == "link":
            logging.info(f"Found links in '{email['subject']}': ['{email['link']}']")
            if not os.path.exists(file_path):
                with open(file_path, "wb") as f:
                    f.write(b"%PDF-1.4\n%mock pdf data\n%%EOF")
                logging.info(f"Downloaded PDF from link: {email['file']}")
                downloaded_files.append(email["file"])
            else:
                logging.info(f"Skipped duplicate link file: {email['file']}")
        else:
            if not os.path.exists(file_path):
                with open(file_path, "w") as f:
                    f.write("Date,Item,Price\n2026-08-01,Asset A,100.5\n")
                logging.info(f"Downloaded attachment: {email['file']}")
                downloaded_files.append(email["file"])
            else:
                logging.info(f"Skipped duplicate attachment: {email['file']}")
                
    return downloaded_files

# ---------------- Main Orchestration ----------------
def main():
    parser = argparse.ArgumentParser(description="Gmail Daily Price List Downloader")
    parser.add_argument("--mock", action="store_true", help="Run in mock/demo mode")
    parser.add_argument("--unread-only", action="store_true", help="Only process unread emails")
    parser.add_argument("--start-date", help="Start date (YYYY-MM-DD) for search query range")
    parser.add_argument("--end-date", help="End date (YYYY-MM-DD) for search query range")
    args = parser.parse_args()
    
    ensure_dir(DOWNLOAD_DIR)
    
    # Configure logging
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    
    # Avoid duplicate handlers if script is re-imported
    if not root_logger.handlers:
        fh = logging.FileHandler(LOG_FILE)
        fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s: %(message)s"))
        root_logger.addHandler(fh)
        
        sh = logging.StreamHandler(sys.stdout)
        sh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s: %(message)s"))
        root_logger.addHandler(sh)
        
        root_logger.addHandler(web_ui_log_handler)
    else:
        if not any(isinstance(h, WebUILogHandler) for h in root_logger.handlers):
            root_logger.addHandler(web_ui_log_handler)
            
    use_mock = args.mock
    if not use_mock and not os.path.exists(CREDS_PATH):
        logging.warning(f"'{CREDS_PATH}' not found in the current directory.")
        logging.warning("Falling back to Mock/Demo Mode. To connect to a real Gmail account, please provide client_secret.json.")
        use_mock = True
        
    if use_mock:
        downloaded = run_mock_mode(DOWNLOAD_DIR, args.start_date, args.end_date)
    else:
        if not GMAIL_API_AVAILABLE:
            logging.error("Google Client API modules are not available. Cannot connect to Gmail.")
            sys.exit(1)
        try:
            logging.info("Authenticating with Gmail API...")
            service = authenticate_gmail()
            logging.info("Searching for matching emails...")
            msg_ids = search_emails(service, query_text=SUBJECT_KEYWORD, unread_only=args.unread_only, start_date=args.start_date, end_date=args.end_date)
            
            downloaded = []
            for msg_id in msg_ids:
                logging.info(f"Processing email ID: {msg_id}")
                downloaded_files = process_email(service, msg_id, DOWNLOAD_DIR)
                if downloaded_files:
                    downloaded.extend(downloaded_files)
        except Exception as e:
            logging.error(f"An error occurred: {e}")
            sys.exit(1)
            
    if downloaded:
        print("\n=== Download Summary ===")
        print(f"Successfully processed and downloaded {len(downloaded)} files:")
        for filename in downloaded:
            print(f" - {filename}")
    else:
        print("\n=== Download Summary ===")
        print("No new files were downloaded.")

if __name__ == '__main__':
    main()
