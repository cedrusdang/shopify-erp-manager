# Shopify ERP Manager

A Python/Tkinter desktop application to manage Shopify products: download to Excel, edit locally, and push changes back to Shopify — with backup, rollback, and upload resume support.

**Contact:** cedrusdang@gmail.com

---

## Features

| Feature | Details |
|---|---|
| Download products | Multi-select fields (scrollable table), required fields always included |
| Discover metafields | Auto-fetch all metafield definitions from your store |
| Export to Excel | Saves as `Shopify_database_264.xlsx`, auto-opens after download |
| Upload to Shopify | Batch update products with rate-limit handling and exponential back-off |
| Resume interrupted uploads | Progress saved after every row — click **Continue Upload** to resume |
| Automatic backup | Timestamped backup created on every download (`backups/shopify_database_YYYYMMDD_HHMMSS.xlsx`) |
| Manual backup & rollback | Create a backup at any time and rollback to any previous version |
| .env support | Load / save Store Domain and API Token from/to `.env` via the Settings tab |
| Login screen | Password protection via `credentials.txt` (default: `admin` / `admin`) |
| Progress bar & logs | Live progress bar and scrollable log for every operation |

---

## Project Structure

```
ERP Shopify/
├── main.py                        # Entry point
├── requirements.txt
├── .env.example                   # Template — copy to .env and fill in
├── .env                           # Your real credentials (git-ignored)
├── credentials.txt                # Login credentials (auto-created)
├── upload_session.json            # Resume state (auto-managed)
├── backups/                       # Timestamped Excel backups
└── shopify_erp/
    ├── __init__.py
    ├── constants.py               # App constants, field lists, help text
    ├── config.py                  # .env loader / saver
    ├── auth.py                    # Login / credential helpers
    ├── api.py                     # Shopify REST API helpers
    ├── backup.py                  # Backup / rollback helpers
    ├── session.py                 # Upload session persistence
    └── ui/
        ├── __init__.py
        ├── app.py                 # Main window + shared state
        ├── login.py               # Login window
        ├── widgets.py             # FieldSelector scrollable widget
        ├── tab_download.py        # Download tab
        ├── tab_upload.py          # Upload tab
        ├── tab_backup.py          # Backup tab
        ├── tab_settings.py        # Settings tab (.env integration)
        └── tab_help.py            # Help / instructions tab
```

---

## Quick Start

### 1. Prerequisites

- Python 3.10+
- Shopify Admin API access token (read/write `products` scope)

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure credentials (optional — you can also type them in the app)

```bash
cp .env.example .env
# Edit .env and fill in your store domain and token
```

### 4. Run

```bash
python main.py
```

Login with `admin` / `admin` (change in `credentials.txt`).

---

## .env format

```dotenv
SHOPIFY_STORE_DOMAIN="your-store.myshopify.com"
SHOPIFY_ACCESS_TOKEN="shpat_xxxxxxxxxxxxxxxxxxxxxxxxxxxx"
```

These values are loaded automatically on startup and can be updated any time from the **Settings** tab.

---

## Changing the Login Password

Edit `credentials.txt` (created automatically in the working directory):

```
admin:your_new_password
```

Format: `username:password`, one per line.

---

## Upload Logic

1. Opens the selected Excel file and reads every row.
2. For each row with a valid `id`, builds a product payload and sends a `PUT` request.
3. Supports top-level fields (`title`, `body_html`, `vendor`, `product_type`, `tags`, `status`, `handle`) and variant fields (`variants.0.sku`, `variants.0.price`, etc.).
4. Retries automatically on HTTP 429 / 5xx with exponential back-off (up to 5 retries, max 32 s wait).
5. Progress is saved after every row. If interrupted, click **Continue Upload** to resume.

---

## License

MIT — free to use and modify.
