# Copilot Instructions

This repository is a Python desktop app for Shopify operations (Tkinter UI).

## Primary Goals
- Keep download and upload flows stable and explicit.
- Preserve user-facing behavior unless a change is requested.
- Prefer minimal, surgical edits over broad refactors.

## Stack
- Python 3.10+
- Tkinter UI in `shopify_erp/ui/`
- API layer in `shopify_erp/api.py`
- Excel I/O via openpyxl

## Important App Flows
- Download products: `shopify_erp/ui/tab_download.py`
- Upload products: `shopify_erp/ui/tab_upload.py`
- Image workflows: `shopify_erp/ui/tab_images_upload.py`
- Shared app shell/status/progress: `shopify_erp/ui/app.py`

## Working Rules
- Keep required field compatibility (`id`, `variants.0.id`, `variants.0.sku`) intact unless explicitly requested.
- Respect retry/backoff behavior for Shopify API calls.
- Avoid changing file names/constants used by UI labels and saved state files unless requested.
- Keep logging messages clear and user-readable.

## Validation Before Finishing
- Run syntax check for changed files:
  - `python -m py_compile <changed_file_1> <changed_file_2> ...`
- If behavior changed, describe impact in simple terms.

## Safe Defaults
- If uncertain where to implement logic:
  - Data fetch/transform -> `api.py`
  - UI interactions/state -> relevant `tab_*.py`
  - App-wide progress/status/cursor -> `ui/app.py`
