# AGENTS Guide

This file helps coding agents work faster and safer in this repository.

## Quick Context
- App type: Python Tkinter desktop ERP for Shopify.
- Entry point: `main.py`.
- Main package: `shopify_erp/`.

## Key Files
- `shopify_erp/api.py`: Shopify API calls, retry/backoff, data shaping.
- `shopify_erp/ui/app.py`: Global app shell, notebook tabs, shared progress/status.
- `shopify_erp/ui/tab_download.py`: Product download to Excel.
- `shopify_erp/ui/tab_upload.py`: Product upload from Excel.
- `shopify_erp/ui/tab_images_download.py`: Image download tools.

## Expected Workflow For Code Changes
1. Read only the files directly related to the request.
2. Implement the smallest viable change.
3. Keep UI text consistent with current wording.
4. Run syntax validation for modified files.
5. Summarize changed behavior clearly.

## Useful Commands
- Run app: `python main.py`
- Syntax check: `python -m py_compile shopify_erp/ui/app.py`
- Project status: `git status -sb`

## Notes
- Local runtime data files can exist (example: `download_field_state.json`).
- Avoid destructive git operations unless explicitly requested.
