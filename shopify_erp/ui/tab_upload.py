"""
Upload tab — push Excel changes back to Shopify.
"""

from __future__ import annotations

import re
import threading
import time
from pathlib import Path
from tkinter import filedialog, scrolledtext
import tkinter as tk
from tkinter import ttk, messagebox

import openpyxl

from ..api import update_product_api
from ..constants import UPDATABLE_TOP
from ..session import save_session, load_session, clear_session


class UploadTab(ttk.Frame):
    def __init__(self, parent: ttk.Notebook, app):
        super().__init__(parent)
        self._app     = app
        self._running = False
        self._build()

    # ──────────────────────────────────────────────────
    def _build(self) -> None:
        # File picker
        frow = ttk.LabelFrame(self, text=" Source Excel File ", padding=8)
        frow.pack(fill=tk.X, padx=8, pady=8)
        self._up_path = tk.StringVar(value="No file selected")
        ttk.Label(
            frow, textvariable=self._up_path,
            foreground="#555", wraplength=620,
        ).pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(frow, text="Browse…", command=self._browse).pack(side=tk.RIGHT)

        # Buttons
        btns = ttk.Frame(self)
        btns.pack(fill=tk.X, padx=8, pady=2)
        ttk.Button(
            btns, text="⬆  Upload to Shopify",
            command=self._start_upload,
        ).pack(side=tk.LEFT, padx=4)
        self._cont_btn = ttk.Button(
            btns, text="▶  Continue Upload",
            command=self._continue_upload, state="disabled",
        )
        self._cont_btn.pack(side=tk.LEFT, padx=4)
        ttk.Button(
            btns, text="✖  Clear Session",
            command=self._clear_session,
        ).pack(side=tk.LEFT, padx=4)

        # Stats + progress
        self._stats = tk.StringVar(value="")
        ttk.Label(
            self, textvariable=self._stats,
            font=("Segoe UI", 9), foreground="#333",
        ).pack(anchor=tk.W, padx=12, pady=2)
        self._prog = ttk.Progressbar(self, mode="determinate")
        self._prog.pack(fill=tk.X, padx=8, pady=2)

        # Log
        ttk.Label(
            self, text="Upload Log:", font=("Segoe UI", 9, "bold"),
        ).pack(anchor=tk.W, padx=8)
        self._log_box = scrolledtext.ScrolledText(
            self, state="disabled", font=("Consolas", 8),
        )
        self._log_box.pack(fill=tk.BOTH, expand=True, padx=8, pady=4)

    # ──────────────────────────────────────────────────
    def check_resume_session(self) -> None:
        sess = load_session()
        if sess:
            self._cont_btn.config(state="normal")
            row   = sess.get("pointer", 0)
            total = sess.get("total", "?")
            self._stats.set(
                f"Saved session: {Path(sess['file']).name} — "
                f"next row {row + 2} / {total}"
            )

    # ──────────────────────────────────────────────────
    def _log(self, msg: str) -> None:
        self._app.log(self._log_box, msg)

    def _browse(self) -> None:
        p = filedialog.askopenfilename(
            title="Select Excel file to upload",
            filetypes=[("Excel", "*.xlsx *.xls"), ("All files", "*.*")],
            parent=self,
        )
        if p:
            self._up_path.set(p)

    # ──────────────────────────────────────────────────
    def _start_upload(self, resume: bool = False) -> None:
        if self._running:
            messagebox.showwarning("Busy", "Upload already in progress.", parent=self)
            return

        store, token = self._app.get_conn()
        if not store:
            return

        if resume:
            sess = load_session()
            if not sess:
                messagebox.showwarning("No Session", "No saved upload session found.", parent=self)
                return
            file_path = Path(sess["file"])
            start_row = sess["pointer"]
        else:
            file_path = Path(self._up_path.get().strip())
            start_row = 0

        if not file_path.exists():
            messagebox.showwarning("File Not Found", f"Cannot find:\n{file_path}", parent=self)
            return

        msg = f"Update Shopify products from:\n{file_path.name}"
        if resume:
            msg += f"\n\nResuming from data row {start_row + 1}."
        msg += "\n\nContinue?"
        if not self._app.confirm("Confirm Upload", msg):
            return

        self._running = True
        self._cont_btn.config(state="disabled")

        def task():
            self._app.start_prog("indeterminate")
            self._log(f"{'Resuming' if resume else 'Starting'} upload: {file_path.name}")
            ok_count = fail_count = 0

            try:
                wb   = openpyxl.load_workbook(file_path, read_only=True, data_only=True)
                ws   = wb.active
                rows = list(ws.iter_rows(values_only=True))
                if not rows:
                    self._log("ERROR: File is empty.")
                    return

                headers   = [str(h or "").strip() for h in rows[0]]
                data_rows = rows[1:]
                total     = len(data_rows)

                if "id" not in headers:
                    self._log("ERROR: 'id' column not found.")
                    messagebox.showerror(
                        "Error",
                        "The Excel file must contain an 'id' column.",
                        parent=self,
                    )
                    return

                self._log(f"Total rows: {total}. Starting from row {start_row + 1}.")
                self._prog.config(maximum=total)
                self._prog["value"] = start_row
                self._app.start_prog("determinate")

                for idx in range(start_row, total):
                    row = data_rows[idx]

                    def rv(col: str) -> str | None:
                        i = headers.index(col) if col in headers else -1
                        val = row[i] if 0 <= i < len(row) else None
                        return str(val) if val not in (None, "") else None

                    product_id = rv("id")
                    if not product_id:
                        self._log(f"Row {idx + 2}: skip (no ID)")
                        continue

                    # Top-level fields
                    prod: dict = {"id": str(product_id)}
                    for col in UPDATABLE_TOP:
                        v = rv(col)
                        if v is not None:
                            prod[col] = v

                    # Variant fields
                    var_map: dict[int, dict] = {}
                    for ci, h in enumerate(headers):
                        m = re.match(r"^variants\.(\d+)\.(.+)$", h)
                        if m and ci < len(row) and row[ci] not in (None, ""):
                            vi  = int(m.group(1))
                            vk  = m.group(2)
                            var_map.setdefault(vi, {})[vk] = str(row[ci])
                    if var_map:
                        prod["variants"] = [
                            vdata for _, vdata in sorted(var_map.items())
                        ]

                    ok, code, err = update_product_api(
                        store, token, str(product_id), {"product": prod}
                    )
                    if ok:
                        ok_count += 1
                    else:
                        fail_count += 1
                        self._log(
                            f"Row {idx + 2}  ID {product_id}: FAIL {code} — {err}"
                        )

                    save_session({"file": str(file_path), "pointer": idx + 1, "total": total})
                    self._prog["value"] = idx + 1
                    self._stats.set(
                        f"Row {idx + 2} / {total + 1}   ✓ {ok_count}   ✗ {fail_count}"
                    )
                    time.sleep(0.5)   # ~2 req/s — stay well under Shopify's 2 req/s limit

                # Done
                self._log(f"Upload complete — Success: {ok_count}, Failed: {fail_count}")
                self._app.set_status(f"Upload done — {ok_count} ok, {fail_count} failed")
                clear_session()
                self._cont_btn.config(state="disabled")
                self._stats.set(f"Finished — {ok_count} ok, {fail_count} failed")
                messagebox.showinfo(
                    "Upload Complete",
                    f"Done!\n\nSuccess: {ok_count}\nFailed:  {fail_count}",
                    parent=self,
                )

            except Exception as exc:
                self._log(f"RUNTIME ERROR: {exc}")
                self._app.set_status("Upload interrupted — progress saved")
                self._cont_btn.config(state="normal")
                messagebox.showerror(
                    "Upload Interrupted",
                    f"Error:\n{exc}\n\n"
                    "Progress was saved.\n"
                    "Click 'Continue Upload' to resume.",
                    parent=self,
                )
            finally:
                self._running = False
                self._app.stop_prog()

        threading.Thread(target=task, daemon=True).start()

    def _continue_upload(self) -> None:
        self._start_upload(resume=True)

    def _clear_session(self) -> None:
        if self._app.confirm("Clear Session", "Clear the saved upload session?"):
            clear_session()
            self._cont_btn.config(state="disabled")
            self._stats.set("")
            self._log("Session cleared.")
