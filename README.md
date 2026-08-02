# Email Automation - Daily Price List Downloader

Automated solution to extract and download daily price list PDFs from Gmail emails. This script connects to Gmail, searches for emails containing "DAILY PRICE LIST" in the subject line, downloads PDF attachments and extracts links, and organizes them in a dedicated directory.

## Features

- **Gmail API Integration**: Securely authenticates with Gmail using OAuth 2.0
- **Smart Email Search**: Finds all emails with "DAILY PRICE LIST" in the subject
- **PDF Download**: Extracts and downloads PDF attachments from emails
- **Link Extraction**: Identifies and downloads PDFs from links within email content
- **Duplicate Prevention**: Avoids re-downloading files that already exist
- **Comprehensive Logging**: Tracks all operations and errors with timestamps
- **Error Handling**: Robust retry logic for network failures and rate limiting
- **Organized Storage**: Saves all files to a dedicated `daily_price_lists/` directory

## Project Structure

```
automation/
├── email_automate.py          # Main automation script
├── requirements.txt           # Python package dependencies
├── client_secret.json         # Google API credentials (excluded from repo)
├── token.pickle              # OAuth token (auto-generated on first run)
├── download_log.txt          # Activity log file
├── README.md                 # This file
└── daily_price_lists/        # Downloaded PDFs directory (auto-created)
```

## Prerequisites

- Python 3.9+
- Gmail account
- Google Cloud Project with Gmail API enabled
- Git (optional, for version control)

## Setup Instructions

### 1. Set Up Google Cloud Console

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select an existing one
3. Enable the **Gmail API**:
   - Click "Enable APIs and Services"
   - Search for "Gmail API"
   - Click "Enable"
4. Create OAuth 2.0 Credentials:
   - Go to "Credentials" in the left sidebar
   - Click "Create Credentials" → "OAuth client ID"
   - Choose "Desktop application"
   - Download the JSON file and rename it to `client_secret.json`
5. Place `client_secret.json` in the project root directory

### 2. Install Python Dependencies

Create and activate a virtual environment (recommended):

```bash
# Create virtual environment
python3 -m venv .venv

# Activate virtual environment
# On macOS/Linux:
source .venv/bin/activate
# On Windows:
.venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### 3. Run the Script

On first run, the script will prompt you to authorize via your browser:

```bash
python email_automate.py
```

Follow the browser prompt to grant Gmail access. The script will then:
- Create `token.pickle` to store your authorization
- Search for matching emails
- Download all PDFs

### 4. Subsequent Runs

Simply run the script again:

```bash
python email_automate.py
```

The script will use the saved token and run without additional authentication steps.

## Configuration

Edit `email_automate.py` to customize the following settings:

```python
EMAIL_ADDRESS = "your_email@gmail.com"      # Your Gmail address
SENDER = "research@morgancapitalgroup.com"  # Optional: filter by sender
SUBJECT_KEYWORD = "DAILY PRICE LIST"        # Email subject filter
TOKEN_PATH = "token.pickle"                  # Token storage location
CREDS_PATH = "client_secret.json"           # Credentials file path
LOG_FILE = "morgancapital_download.log"     # Log file name
DOWNLOAD_DIR = "daily_price_lists"          # Download directory
```

### Optional Enhancements

The script supports several optional features (disabled by default):

- **Mark emails as read** after processing
- **Move processed emails** to a specific folder
- **Schedule with cron** (Linux/macOS) or Task Scheduler (Windows)
- **Send summary email** after completing downloads

See inline comments in `email_automate.py` for implementation details.

## Usage

### Basic Usage

```bash
python email_automate.py
```

### Process Unread Emails Only

By default, the script processes all emails matching the search criteria. To process only unread emails, modify the search query in the `search_emails()` function:

```python
query = f'subject:({SUBJECT_KEYWORD}) is:unread'
```

### View Logs

Check the download activity and any errors:

```bash
cat download_log.txt
```

Or check the terminal output during execution (logs are printed to both file and console).

## Output

### Downloaded Files

All PDFs are saved to the `daily_price_lists/` directory with cleaned filenames:

```
daily_price_lists/
├── DAILY_PRICE_LIST_JUNE_04_2026.pdf
├── DAILY_PRICE_LIST_MAY_29_2026.pdf
├── DAILY_PRICE_LIST_MAY_26_2026.pdf
└── ...
```

### Log File

The `download_log.txt` file contains timestamped records of:
- Emails found and processed
- Successfully downloaded files
- Duplicate files skipped
- Links extracted and processed
- Errors encountered with details

Example log entries:

```
2026-06-04 21:04:14,228 INFO: Found 246 matching emails.
2026-06-04 21:04:16,931 INFO: Downloaded PDF from link: DAILY_PRICE_LIST_JUNE_04_2026.pdf
2026-06-04 21:04:17,386 INFO: Found links in 'DAILY PRICE LIST - MAY 29, 2026.'
```

## Troubleshooting

### `ModuleNotFoundError: No module named 'googleapiclient'`

**Solution**: Ensure your virtual environment is activated and dependencies are installed:
```bash
source .venv/bin/activate  # macOS/Linux
pip install -r requirements.txt
```

### `invalid_grant: Bad Request` Error

**Solution**: The OAuth token has expired. Delete `token.pickle` and run the script again:
```bash
rm token.pickle
python email_automate.py
```

### `FileNotFoundError: client_secret.json`

**Solution**: Ensure `client_secret.json` from Google Cloud Console is placed in the project root directory.

### Gmail API Not Enabled

**Solution**: Go to Google Cloud Console, select your project, and enable the Gmail API in the APIs & Services section.

### No Emails Found

**Possible causes**:
- The email subject doesn't match `SUBJECT_KEYWORD` (default: "DAILY PRICE LIST")
- The email sender doesn't match `SENDER` (if filtering by sender)
- The email account used for authentication is different

Check your email manually and adjust the search query if needed.

### Network Errors or Rate Limiting

The script automatically retries failed requests with exponential backoff. If errors persist:
- Check your internet connection
- Wait a few minutes before running again
- Check Google API quotas in the Cloud Console

## Security Considerations

- **Never commit** `client_secret.json` or `token.pickle` to version control
- Add these files to `.gitignore`:
  ```
  client_secret.json
  token.pickle
  *.log
  ```
- The script only requests `gmail.readonly` scope (read-only access)
- Credentials are stored locally and never shared

## Performance

- **Email Search**: Processes up to 100 emails per API call
- **Retry Logic**: Failed requests retry up to 3 times with exponential backoff
- **Duplicate Detection**: Skips files already in `daily_price_lists/`
- **Typical Runtime**: 30-60 seconds for 246 emails (varies by file size and network)

## System Requirements

| Component | Requirement |
|-----------|-------------|
| Python | 3.9+ |
| Memory | ~100MB |
| Disk Space | Depends on PDF size (typically 10-50MB) |
| Network | Internet connection required |
| OS | macOS, Linux, Windows |

## Dependencies

- `google-api-python-client` - Gmail API client
- `google-auth-httplib2` - HTTP authentication
- `google-auth-oauthlib` - OAuth 2.0 flow
- `requests` - HTTP library for link extraction
- `tenacity` - Retry logic with exponential backoff

See `requirements.txt` for versions.

## Scheduling (Optional)

### Linux/macOS - Using Cron

Add to crontab (`crontab -e`):

```bash
# Run daily at 9 AM
0 9 * * * cd /path/to/automation && source .venv/bin/activate && python email_automate.py
```

### Windows - Using Task Scheduler

1. Open Task Scheduler
2. Create a new basic task
3. Set trigger (e.g., daily at 9 AM)
4. Set action to run: `C:\path\to\automation\.venv\Scripts\python.exe email_automate.py`
5. Set working directory: `C:\path\to\automation`

## Future Enhancements

Potential improvements for future versions:

- [ ] Web UI for configuration and monitoring
- [ ] Email notifications on completion
- [ ] Support for filtering by date range
- [ ] Automatic file organization by date
- [ ] Webhook integration for external systems
- [ ] Database logging instead of text file
- [ ] Support for multiple email sources
- [ ] Cloud storage integration (Google Drive, S3, etc.)

## Troubleshooting Checklist

- [ ] Python version 3.9+?
- [ ] Virtual environment activated?
- [ ] Dependencies installed? (`pip install -r requirements.txt`)
- [ ] `client_secret.json` in project root?
- [ ] Gmail API enabled in Google Cloud Console?
- [ ] Correct Gmail address in `EMAIL_ADDRESS` variable?
- [ ] Internet connection working?

## Support & Issues

For issues or questions:

1. Check the logs: `cat download_log.txt`
2. Verify all prerequisites are installed
3. Review the Troubleshooting section above
4. Check Google Cloud Console quotas and status

## License

This project is provided as-is for personal or internal use.

## Related Resources

- [Gmail API Documentation](https://developers.google.com/gmail/api/guides)
- [Google Auth Library for Python](https://google-auth.readthedocs.io/)
- [Google Cloud Console](https://console.cloud.google.com/)
- [OAuth 2.0 Documentation](https://oauth.net/2/)

---

**Last Updated**: June 4, 2026  
**Python Version**: 3.9+  
**Status**: Active
