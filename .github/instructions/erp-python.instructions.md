---
applyTo: "shopify_erp/**/*.py,main.py,tests/**/*.py"
---

Project-specific Python instructions:

1. Preserve existing Tkinter interaction patterns.
2. Keep long-running tasks in worker threads to avoid UI freeze.
3. Route Shopify API requests through `shopify_erp/api.py` when possible.
4. Keep user messages concise and actionable.
5. Do not silently remove fields from Excel/export headers unless asked.
6. For download/upload changes, keep progress updates (`start_prog`, `set_status`, `stop_prog`) coherent.
7. For image flows, preserve deterministic naming and predictable folder layout.
8. Prefer explicit error handling with readable logs over broad implicit behavior.
9. Keep compatibility with current constants in `shopify_erp/constants.py`.
10. Validate syntax of modified files before finalizing.
