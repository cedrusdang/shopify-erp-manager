"""
Application-wide constants, field lists, and instruction text.
"""

APP_TITLE = "Shopify ERP Manager"
APP_VER   = "1.0"
CONTACT   = "cedrusdang@gmail.com"
API_VER   = "2024-10"
DEF_NAME  = "Shopify_database_264"

REQUIRED_FIELDS: list[str] = [
    "id",
    "title",
    "vendor",
    "product_type",
    "tags",
    "status",
]

OPTIONAL_FIELDS: list[str] = [
    "body_html",
    "handle",
    "created_at",
    "updated_at",
    "published_at",
    "template_suffix",
    "published_scope",
    "admin_graphql_api_id",
    "variants.0.id",
    "variants.0.sku",
    "variants.0.title",
    "variants.0.price",
    "variants.0.compare_at_price",
    "variants.0.inventory_quantity",
    "variants.0.weight",
    "variants.0.weight_unit",
    "variants.0.barcode",
    "variants.0.option1",
    "variants.0.option2",
    "variants.0.option3",
    "variants.0.taxable",
    "variants.0.requires_shipping",
    "images.0.src",
    "images.0.alt",
    "options.0.name",
    "options.0.values.0",
]

# Top-level product keys that are safe to send back via PUT
UPDATABLE_TOP: set[str] = {
    "title", "body_html", "vendor", "product_type",
    "tags", "status", "handle", "published",
}

INSTRUCTIONS = f"""\
SHOPIFY ERP MANAGER — User Guide  v{APP_VER}
Contact: {CONTACT}
══════════════════════════════════════════════

▌ CONNECT (Connection bar at the top)
  • Enter Store Domain  (e.g.  mystore.myshopify.com)
    and your Admin API Access Token.
  • Click "Test Connection" to verify before proceeding.
  • Credentials are NEVER written to disk unless you
    explicitly save them in the Settings tab.

▌ SETTINGS TAB
  • Load credentials from / save credentials to  .env
  • Edits are validated before saving.
  • The .env file is excluded from git by .gitignore.

▌ DOWNLOAD  (Shopify → Excel)
  1. Tick the product fields you want to export.
     Required fields are always included and cannot be removed.
  2. Click "Discover Fields" to auto-fetch metafield
     definitions from your store and add them to the list.
  3. Click "Download Products" — all pages are fetched
     automatically.
  4. The file is saved as  {DEF_NAME}.xlsx  and opened.
  5. A timestamped backup is created automatically.

▌ UPLOAD  (Excel → Shopify)
  1. Click "Browse" to select an Excel file
     (must have an  id  column).
  2. Click "Upload to Shopify".
     Products are updated with automatic rate-limit retries.
  3. If an error interrupts the run, progress is auto-saved.
     Click "Continue Upload" to resume.
  4. All errors appear in the Upload Log area.

▌ BACKUP & ROLLBACK
  • A backup is created automatically on every download.
  • Naming: shopify_database_YYYYMMDD_HHMMSS.xlsx
  • In the Backup tab, select any backup and click
    "Rollback" to restore it as {DEF_NAME}.xlsx.
  • Manual backup can be created at any time.

▌ LOGIN
  • Credentials stored in  credentials.txt
  • Default: username = admin  /  password = admin
  • Edit credentials.txt to change passwords.

▌ SAFETY
  • Every destructive action requires Yes/No confirmation.
  • Progress bar and log area show live status.
  • Rate-limit (HTTP 429) is handled automatically with
    exponential back-off.

══════════════════════════════════════════════
  Contact: {CONTACT}
══════════════════════════════════════════════
"""
