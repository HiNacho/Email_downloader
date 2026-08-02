# 📕 Email Stock Price Downloader & ETL Dashboard

An automated, ultra-fast **Extract, Transform, and Load (ETL)** pipeline and interactive dashboard that monitors your Gmail inbox for NGX (Nigerian Exchange) Daily Price Lists, parses PDF tables directly in-memory, loads them into an SQLite database, and provides an elegant dark-mode web query portal.

> [!NOTE]
> **Zero Local Disk Clutter**: The downloader functions entirely in-memory. PDF binaries are fetched and parsed directly via raw bytes streams, saving them straight to the relational database without writing files to your hard drive.

---

## 🛠️ Technology Stack & Tools Used

| Tool / Technology | Purpose | Key Benefit |
| :--- | :--- | :--- |
| **Python 3.9+** | Core programming language | General backend processing and data logic |
| **SQLite 3** | Local relational database | Light, zero-configuration structured data storage |
| **Gmail API** | Mailbox scanning & fetch | Official, secure OAuth 2.0 connection to Gmail |
| **PyPDF** | PDF text extraction | High-speed text layout parser for NGX price tables |
| **Concurrency (`ThreadPoolExecutor`)** | Multi-threaded downloading | Fast, parallel link checking and binary downloading |
| **Vanilla CSS & Glassmorphic UI** | UI Dashboard frontend styling | Sleek, modern responsive dark-mode portal |
| **Zero-Dependency API Server** | Custom backend controller | Python `http.server` built-in handler (low footprint) |

---

## 📁 Organized Folder Structure

The project directory is structured cleanly to isolate business logic, templates, static placeholders, and data files:

```
Email_downloader/
├── data/                     # Data storage (git-ignored)
│   ├── raw/                  # Placeholder folder for manual raw PDFs
│   ├── processed/            # Structured SQLite database (stocks.db)
│   └── external/             # Third-party assets
│
├── docs/                     # Documentation and notes
├── tests/                    # Unit testing files
├── notebook/                 # EDA & experimental Jupyter notebooks
│
├── src/                      # Source Code
│   ├── components/           # UI Components
│   │   └── index.html        # Elegant glassmorphic query interface
│   ├── utils/                # ETL & helper modules
│   │   ├── __init__.py       # Package indicator
│   │   ├── email_automate.py # Concurrency link & Gmail sync engine
│   │   └── etl.py            # SQLite schema, regex parser, mock seeder
│   └── main.py               # Main HTTP web server & entry point
│
├── .gitignore                # Restricts databases, pickle tokens, and client secrets
├── Procfile                  # Startup configuration file for Railway hosting
├── README.md                 # Project summary and documentation
└── requirements.txt          # Third-party python dependencies
```

---

## 🚀 Setup & Installation

### 1. Place API Credentials
Download your OAuth 2.0 Credentials client secret file from the [Google Cloud Console](https://console.cloud.google.com/), rename it to `client_secret.json`, and place it in the root folder of this project.

### 2. Install Dependencies
Run the command below in your virtual environment to install all required libraries:
```bash
pip install -r requirements.txt
```

### 3. Run the Dashboard
Start the local server by running the entry point script:
```bash
python3 src/main.py
```
*(The script will automatically launch your default web browser and open the dashboard at `http://localhost:8080`)*

---

## 🖥️ Feature Tour

### 📥 Real-Time In-Memory Sync
Toggle keyword filters, unread email tags, or specify date ranges to download and extract data. The python sync engine runs base64 attachment decoders and concurrent link resolvers, loading all records directly to your database with live log feedback.

### 📊 SQLite Database Explorer
Search through thousands of historical stock records by choosing the company name (e.g. `MTNN`, `ACCESSCORP`, etc.) and date range. A clean data table lists opening, closing, high, low, price change, trade deals, and volumes.

### 📥 One-Click CSV Downloader
Export your queried stock data directly onto your Mac by clicking the **CSV** button next to Search to download a structured spreadsheet instantly.

---

## 🔒 Security
* Sensitive cache files (`token.pickle`), databases (`stocks.db`), and secrets (`client_secret.json`) are automatically excluded from Git commits via `.gitignore`.
* File permissions on credentials and database binaries are restricted to owner-only read/write access (`chmod 600`) to prevent local snooping.
