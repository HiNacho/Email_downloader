Gmail Daily Price List Automation Script
=======================================

Directory Structure:
--------------------
automation/
├── email_automate.py
├── requirements.txt
├── client_secret.json   # (download from Google Cloud Console)
├── token.pickle         # (auto-generated after first run)
├── download_log.txt     # (auto-generated)
└── daily_price_lists/   # (auto-created, contains downloaded files)

Setup Instructions:
-------------------
1. Enable Gmail API in Google Cloud Console:
   - https://console.cloud.google.com/
   - Create a project, enable Gmail API, create OAuth credentials (Desktop app).
   - Download client_secret.json and place in this directory.

2. Install dependencies:
   - Run: pip install -r requirements.txt

3. Run the script:
   - python email_automate.py
   - On first run, authenticate in your browser.

4. Files will be saved in daily_price_lists/ and logs in download_log.txt.

Options:
--------
- To process all emails (not just unread), set unread_only=False in main().

Error Handling:
---------------
- Network, permission, and rate limit errors are logged in download_log.txt.
- Google Drive links are skipped and logged.

Optional Enhancements (not enabled by default):
-----------------------------------------------
- Auto-mark processed emails as "read"
- Move processed emails to a folder like "/Daily Price Lists"
- Schedule with cron or Windows Task Scheduler
- Send summary email after downloading files

See comments in email_automate.py for further customization.
