"""
Application-wide constants, field lists, and instruction text.
"""

APP_TITLE = "Shopify ERP Manager"
APP_VER   = "1.0"
CONTACT   = "cedrusdang@gmail.com"
API_VER   = "2024-10"
DEF_NAME  = "Shopify_database_264"
DATABASE_FILE = f"{DEF_NAME}.xlsx"
IMAGE_DIR = "product_images"
DEFAULT_SKU = "default"

REQUIRED_FIELDS: list[str] = [
    "id",
    "title",
    "handle",
    "variants.0.sku",
]

INSTRUCTIONS = f"""\
SHOPIFY ERP MANAGER — User Guide  v{APP_VER}
Contact: {CONTACT}
══════════════════════════════════════════════

QUICK START (MOST IMPORTANT)
  (1) Open Settings tab and fill Store Domain, Client ID, Client Secret.
    Optional: save a profile for each store.
  (2) Click Apply in Settings (or manually fill connection bar).
  (3) Click "Get API Token" in top connection bar.
  (4) Click "Test" to verify connection.
  (5) Go to Download / Upload / Images tab and run your task.

▌ CONNECT (Top connection bar)
  • Fill Store Domain, Client ID, Client Secret.
  • Click "(2) Get API Token".
  • Click "(2b) Test" before download/upload.
  • Product read/write operations run on GraphQL Admin API.
  • Use "Show API Token" and "Copy Token" when needed.

▌ SETTINGS TAB
  • Save multiple stores as profiles (Save/Update, Load, Apply, Delete).
  • Load credentials from / save credentials to .env.
  • Edits are validated before saving.
  • The .env file is excluded from git by .gitignore.

▌ DOWNLOAD  (Shopify → Excel)
  1. Tick fields you want to export.
     Required fields are always included and cannot be removed.
  2. Optional: use Selection Presets to save/load named field sets.
  2. Click "(3a) Discover More Fields" to auto-fetch metafield
     definitions from your store and add them to the list.
  3. Set Download Scope:
     • All Pages  (download everything)
     • Single Page (enter Page #)
  4. Click "(3b) Download Products".
  5. The file is saved as  {DEF_NAME}.xlsx  and opened.
  6. A timestamped backup is created automatically.

▌ UPLOAD  (Excel → Shopify)
  1. Uses fixed file  {DEF_NAME}.xlsx  (must contain an  id  column).
  2. Choose upload columns in "Upload Only Selected Fields".
  2. Click "(4b) Upload to Shopify".
     Products are updated with automatic rate-limit retries.
  3. If an error interrupts the run, progress is auto-saved.
     Click "(4c) Continue Upload" to resume.
  4. All errors appear in the Upload Log area.

▌ IMAGES TAB  (Download / Upload / Scan / Delete)
  • Download Images:
    - Choose image URL field mode:
      All image src fields OR Single field.
    - Images are downloaded to {IMAGE_DIR}.
  • Upload Images by SKU:
    - Uploads local files using SKU-prefix matching.
  • Scan Folder Coverage:
    - Shows rows with HAS / MISSING image files in folder.
  • Delete Selected SKU Images:
    - Deletes local files for selected rows.
  • Manifest file:
    - {IMAGE_DIR}/image_sources.txt stores source URL info
      (file name, product id, sku, field, source URL).
  • Downloaded image naming:
    - sku_<field_name> (example: sku_img_0)

▌ LIVE DATABASE (Bottom Panel + Full Tab)
  • Always shows the fixed local database file.
  • Inline edit supported by double-clicking a cell.
  • Search supports All Columns or selected column.
  • Paging supported:
    - Shows total rows and current page.
    - Prev / Next / Go to page.

▌ BACKUP & ROLLBACK
  • A backup is created automatically on every download.
  • Naming: shopify_database_YYYYMMDD_HHMMSS.xlsx
  • In the Backup tab, select any backup and click
    "Rollback" to restore it as {DEF_NAME}.xlsx.
  • Manual backup can be created at any time.

▌ LOGIN
  • Password prompt is disabled.
  • Click Login to enter.

▌ SAFETY
  • Dangerous actions require one Yes/No confirmation.
  • Progress bar and log area show live status.
  • Rate-limit (HTTP 429) is handled automatically with
    exponential back-off.

══════════════════════════════════════════════
  Contact: {CONTACT}
══════════════════════════════════════════════
"""
