"""
Download tab — fetch products from Shopify and save to Excel.
"""

from __future__ import annotations

import threading
from datetime import datetime
from pathlib import Path
from tkinter import scrolledtext
import tkinter as tk
from tkinter import ttk, messagebox

import openpyxl
from openpyxl.styles import Font

from ..api import fetch_all_products, fetch_metafield_definitions, get_by_path
from ..backup import create_backup, open_file
from ..constants import DEF_NAME, REQUIRED_FIELDS, OPTIONAL_FIELDS
from ..ui.widgets import FieldSelector


class DownloadTab(ttk.Frame):
    def __init__(self, parent: ttk.Notebook, app):
        super().__init__(parent)
        self._app = app
        self._running = False
        self._build()

    # ──────────────────────────────────────────────────
    def _build(self) -> None:
        # Left: field selector
        left = ttk.Frame(self)
        left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=8, pady=8)
        self.fields = FieldSelector(left, REQUIRED_FIELDS, OPTIONAL_FIELDS)
        self.fields.pack(fill=tk.BOTH, expand=True)
        ttk.Button(
            left,
            text="Discover Fields from Shopify API",
            command=self._discover_fields,
        ).pack(fill=tk.X, pady=4)

        # Right: controls
        right = ttk.LabelFrame(self, text=" Actions ", padding=10, width=240)
        right.pack(side=tk.RIGHT, fill=tk.Y, padx=(0, 8), pady=8)
        right.pack_propagate(False)

        ttk.Label(right, text="Output Filename:").pack(anchor=tk.W)
        self._fname = tk.StringVar(value=DEF_NAME)
        ttk.Entry(right, textvariable=self._fname).pack(fill=tk.X, pady=3)
        ttk.Label(
            right, text="(.xlsx will be appended)",
            foreground="gray", font=("Segoe UI", 7),
        ).pack(anchor=tk.W)

        ttk.Separator(right).pack(fill=tk.X, pady=10)
        ttk.Button(
            right, text="⬇  Download Products",
            command=self._start_download,
        ).pack(fill=tk.X, pady=3)
        ttk.Button(
            right, text="📂  Open Current File",
            command=self._open_current,
        ).pack(fill=tk.X, pady=3)

        ttk.Separator(right).pack(fill=tk.X, pady=10)
        ttk.Label(
            right, text="Last Downloaded:",
            font=("Segoe UI", 8, "bold"),
        ).pack(anchor=tk.W)
        self._last_dl = tk.StringVar(value="—")
        ttk.Label(
            right, textvariable=self._last_dl,
            foreground="#555", wraplength=210, font=("Segoe UI", 8),
        ).pack(anchor=tk.W, pady=2)

        ttk.Label(
            right, text="Log:", font=("Segoe UI", 8, "bold"),
        ).pack(anchor=tk.W, pady=(10, 0))
        self._log_box = scrolledtext.ScrolledText(
            right, state="disabled", font=("Consolas", 8), height=16
        )
        self._log_box.pack(fill=tk.BOTH, expand=True)

    # ──────────────────────────────────────────────────
    def current_xlsx(self) -> Path:
        n = self._fname.get().strip() or DEF_NAME
        return Path(n if n.endswith(".xlsx") else n + ".xlsx")

    def _log(self, msg: str) -> None:
        self._app.log(self._log_box, msg)

    # ──────────────────────────────────────────────────
    def _discover_fields(self) -> None:
        store, token = self._app.get_conn()
        if not store:
            return

        def task():
            self._app.start_prog()
            self._log("Discovering metafield definitions…")
            try:
                mf    = fetch_metafield_definitions(store, token)
                added = self.fields.add_optional_fields(mf)
                self._log(
                    f"Found {len(mf)} definitions. {added} new fields added."
                )
                self._app.set_status(f"Discovered {len(mf)} metafield definitions")
            except Exception as exc:
                self._log(f"Error: {exc}")
                messagebox.showerror("Error", str(exc), parent=self)
            finally:
                self._app.stop_prog()

        threading.Thread(target=task, daemon=True).start()

    # ──────────────────────────────────────────────────
    def _start_download(self) -> None:
        if self._running:
            messagebox.showwarning("Busy", "Download already in progress.", parent=self)
            return

        store, token = self._app.get_conn()
        if not store:
            return

        fields = self.fields.get_selected()
        if not fields:
            messagebox.showwarning("No Fields", "Select at least one field.", parent=self)
            return

        out = self.current_xlsx()
        if not self._app.confirm(
            "Confirm Download",
            f"Fetch ALL products from Shopify and save to:\n"
            f"{out.resolve()}\n\n"
            f"Existing file will be overwritten.\n\nContinue?",
        ):
            return

        self._running = True

        def task():
            self._app.start_prog("indeterminate")
            self._log("Starting download…")
            try:
                products = fetch_all_products(
                    store, token,
                    on_progress=lambda m: (self._log(m), self._app.set_status(m)),
                )
                total = len(products)
                self._log(f"Fetched {total} products. Building Excel…")
                self._app.start_prog("determinate")

                wb = openpyxl.Workbook()
                ws = wb.active
                ws.title = "Products"
                for ci, f in enumerate(fields, 1):
                    cell = ws.cell(row=1, column=ci, value=f)
                    cell.font = Font(bold=True)

                BATCH = 500
                for start in range(0, total, BATCH):
                    chunk = products[start:start + BATCH]
                    for ri, p in enumerate(chunk, start + 2):
                        for ci, f in enumerate(fields, 1):
                            ws.cell(row=ri, column=ci, value=str(get_by_path(p, f)))
                    self._app.set_prog_value(min(start + BATCH, total), total)
                    self._app.set_status(
                        f"Writing rows {start + 2}–{min(start + BATCH + 1, total + 1)}…"
                    )

                wb.save(out)
                self._log(f"Saved: {out.resolve()}")

                bk = create_backup(out)
                self._log(f"Backup: {bk.name}")
                self._app.notify_backup_created()

                ts = datetime.now().strftime("%Y-%m-%d  %H:%M:%S")
                self._last_dl.set(ts)
                self._log(f"Done! {total} products, {len(fields)} fields.")
                self._app.set_status(f"Download complete — {total} products")
                open_file(out)

            except Exception as exc:
                self._log(f"ERROR: {exc}")
                self._app.set_status("Download failed")
                messagebox.showerror("Download Error", str(exc), parent=self)
            finally:
                self._running = False
                self._app.stop_prog()

        threading.Thread(target=task, daemon=True).start()

    def _open_current(self) -> None:
        p = self.current_xlsx()
        if not open_file(p):
            messagebox.showwarning(
                "Not Found", f"File not found:\n{p.resolve()}", parent=self
            )
