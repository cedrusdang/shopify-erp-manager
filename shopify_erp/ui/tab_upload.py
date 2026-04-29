"""
Upload tab — push Excel changes back to Shopify.
"""

from __future__ import annotations

import base64
import re
import threading
import time
from pathlib import Path
from tkinter import scrolledtext
import tkinter as tk
from tkinter import ttk, messagebox

import openpyxl

from ..api import update_product_api
from ..constants import DATABASE_FILE, DEFAULT_SKU, IMAGE_DIR, UPDATABLE_TOP
from ..session import save_session, load_session, clear_session


class UploadTab(ttk.Frame):
    def __init__(self, parent: ttk.Notebook, app):
        super().__init__(parent)
        self._app     = app
        self._running = False
        self._upload_col_vars: dict[str, tk.BooleanVar] = {}
        self._upload_headers: list[str] = []
        self._build()

    # ──────────────────────────────────────────────────
    def _build(self) -> None:
        ttk.Label(
            self,
            text="(4) Upload fixed database file to Shopify",
            font=("Segoe UI", 10, "bold"),
            foreground="#0f6b45",
        ).pack(anchor=tk.W, padx=10, pady=(8, 0))

        # Fixed file display
        frow = ttk.LabelFrame(self, text=" Source Excel File (fixed) ", padding=8)
        frow.pack(fill=tk.X, padx=8, pady=8)
        self._up_path = tk.StringVar(value=DATABASE_FILE)
        ttk.Label(
            frow, textvariable=self._up_path,
            foreground="#555", wraplength=620,
        ).pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Label(
            frow,
            text="No browsing allowed",
            foreground="#888",
            font=("Segoe UI", 8, "italic"),
        ).pack(side=tk.RIGHT)

        # Upload field selection
        selector = ttk.LabelFrame(self, text=" Upload Only Selected Fields ", padding=8)
        selector.pack(fill=tk.BOTH, padx=8, pady=(0, 6))
        selector_top = ttk.Frame(selector)
        selector_top.pack(fill=tk.X, pady=(0, 4))
        ttk.Label(
            selector_top,
            text="Choose which columns to upload. Only selected columns are sent.",
            foreground="#555",
            font=("Segoe UI", 8),
        ).pack(side=tk.LEFT)
        ttk.Button(selector_top, text="Load Columns", command=self._load_upload_columns).pack(side=tk.RIGHT, padx=(4, 0))
        ttk.Button(selector_top, text="Clear All", command=self._clear_upload_cols).pack(side=tk.RIGHT, padx=(4, 0))
        ttk.Button(selector_top, text="Select All", command=self._select_all_upload_cols).pack(side=tk.RIGHT)

        self._upload_col_canvas = tk.Canvas(selector, borderwidth=0, highlightthickness=0, height=122)
        upload_col_vsb = ttk.Scrollbar(selector, orient="vertical", command=self._upload_col_canvas.yview)
        self._upload_col_canvas.configure(yscrollcommand=upload_col_vsb.set)
        upload_col_vsb.pack(side=tk.RIGHT, fill=tk.Y)
        self._upload_col_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self._upload_col_inner = ttk.Frame(self._upload_col_canvas)
        self._upload_col_win = self._upload_col_canvas.create_window((0, 0), window=self._upload_col_inner, anchor="nw")
        self._upload_col_inner.bind(
            "<Configure>",
            lambda _e: self._upload_col_canvas.configure(scrollregion=self._upload_col_canvas.bbox("all")),
        )
        self._upload_col_canvas.bind(
            "<Configure>",
            lambda e: self._upload_col_canvas.itemconfig(self._upload_col_win, width=e.width),
        )

        # Buttons
        btns = ttk.Frame(self)
        btns.pack(fill=tk.X, padx=8, pady=2)
        ttk.Button(
            btns, text="(4b) Upload to Shopify",
            command=self._start_upload,
            style="Primary.TButton",
        ).pack(side=tk.LEFT, padx=4)
        self._cont_btn = ttk.Button(
            btns, text="(4c) Continue Upload",
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

        self._load_upload_columns()

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

    def _safe_sku(self, value: str) -> str:
        sku = re.sub(r"[^A-Za-z0-9._-]+", "_", (value or "").strip())
        return (sku[:80] or "product")

    def _build_images_payload_from_folder(self, sku: str) -> list[dict]:
        """Fallback: load local images by SKU prefix from IMAGE_DIR and convert to attachments."""
        folder = Path(IMAGE_DIR)
        if not folder.exists():
            return []

        prefix = self._safe_sku(sku)
        files = sorted([p for p in folder.glob(f"{prefix}*.*") if p.is_file()])
        payload: list[dict] = []
        for p in files:
            try:
                encoded = base64.b64encode(p.read_bytes()).decode("ascii")
                payload.append({"attachment": encoded, "filename": p.name})
            except Exception:
                continue
        return payload

    def _is_uploadable_header(self, h: str) -> bool:
        if h in UPDATABLE_TOP:
            return True
        if re.match(r"^variants\.\d+\..+$", h):
            return True
        if re.match(r"^images\.\d+\.(src|alt)$", h):
            return True
        return False

    def _load_upload_columns(self) -> None:
        file_path = Path(DATABASE_FILE)
        if not file_path.exists():
            self._log(f"Upload columns: waiting for {file_path.name}")
            return

        try:
            wb = openpyxl.load_workbook(file_path, read_only=True, data_only=True)
            ws = wb.active
            rows = list(ws.iter_rows(values_only=True, min_row=1, max_row=1))
            if not rows:
                return
            headers = [str(h or "").strip() for h in rows[0]]
        except Exception as exc:
            self._log(f"Upload columns load error: {exc}")
            return

        keep_checked = {
            h for h, var in self._upload_col_vars.items() if var.get()
        }

        self._upload_headers = [h for h in headers if self._is_uploadable_header(h)]
        self._upload_col_vars.clear()
        for w in self._upload_col_inner.winfo_children():
            w.destroy()

        if not self._upload_headers:
            ttk.Label(
                self._upload_col_inner,
                text="No uploadable columns found in DB file.",
                foreground="#777",
            ).pack(anchor=tk.W, padx=4, pady=4)
            return

        for h in self._upload_headers:
            checked = h in keep_checked if keep_checked else True
            var = tk.BooleanVar(value=checked)
            self._upload_col_vars[h] = var
            ttk.Checkbutton(self._upload_col_inner, text=h, variable=var).pack(anchor=tk.W, padx=6)

        self._upload_col_inner.update_idletasks()
        self._log(f"Upload columns ready: {len(self._upload_headers)}")

    def _select_all_upload_cols(self) -> None:
        for var in self._upload_col_vars.values():
            var.set(True)

    def _clear_upload_cols(self) -> None:
        for var in self._upload_col_vars.values():
            var.set(False)

    def _selected_upload_cols(self) -> set[str]:
        return {h for h, var in self._upload_col_vars.items() if var.get()}

    # ──────────────────────────────────────────────────
    def _start_upload(self, resume: bool = False) -> None:
        if self._running:
            messagebox.showwarning("Busy", "Upload already in progress.", parent=self)
            return

        store, token = self._app.get_conn()
        if not store:
            return

        file_path = Path(DATABASE_FILE)
        if resume:
            sess = load_session()
            if not sess:
                messagebox.showwarning("No Session", "No saved upload session found.", parent=self)
                return
            start_row = sess["pointer"]
        else:
            start_row = 0

        if not file_path.exists():
            messagebox.showwarning("File Not Found", f"Cannot find:\n{file_path}", parent=self)
            return

        selected_cols = self._selected_upload_cols()
        if not selected_cols:
            messagebox.showwarning(
                "No Upload Fields",
                "Please select at least one upload field before running upload.",
                parent=self,
            )
            return

        msg = f"Update Shopify products from:\n{file_path.name}"
        if resume:
            msg += f"\n\nResuming from data row {start_row + 1}."
        msg += f"\n\nSelected upload columns: {len(selected_cols)}"
        msg += "\n\nContinue?"
        if not self._app.confirm_danger("Confirm Upload", msg):
            return

        self._running = True
        self._cont_btn.config(state="disabled")

        def task():
            self._app.start_prog("indeterminate")
            self._log(f"{'Resuming' if resume else 'Starting'} upload: {file_path.name}")
            ok_count = fail_count = skip_count = 0

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
                self._log(f"Selected upload columns: {len(selected_cols)}")
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
                        if col not in selected_cols:
                            continue
                        v = rv(col)
                        if v is not None:
                            prod[col] = v

                    # Variant fields
                    var_map: dict[int, dict] = {}
                    for ci, h in enumerate(headers):
                        m = re.match(r"^variants\.(\d+)\.(.+)$", h)
                        if m and h in selected_cols and ci < len(row) and row[ci] not in (None, ""):
                            vi  = int(m.group(1))
                            vk  = m.group(2)
                            var_map.setdefault(vi, {})[vk] = str(row[ci])
                    if var_map:
                        prod["variants"] = [
                            vdata for _, vdata in sorted(var_map.items())
                        ]

                    # Image fields from columns like:
                    # images.0.src, images.0.alt, images.1.src, images.1.alt
                    image_map: dict[int, dict] = {}
                    for ci, h in enumerate(headers):
                        m = re.match(r"^images\.(\d+)\.(src|alt)$", h)
                        if m and h in selected_cols and ci < len(row) and row[ci] not in (None, ""):
                            ii = int(m.group(1))
                            ik = m.group(2)
                            image_map.setdefault(ii, {})[ik] = str(row[ci]).strip()

                    if image_map:
                        images_payload = []
                        for _, img in sorted(image_map.items()):
                            src = img.get("src", "").strip()
                            if not src:
                                # Shopify requires src for image create/update payload entries.
                                continue
                            one: dict[str, str] = {}
                            if src.lower().startswith("http://") or src.lower().startswith("https://"):
                                one["src"] = src
                            else:
                                local_path = Path(src)
                                if not local_path.is_absolute():
                                    local_path = (Path.cwd() / local_path).resolve()
                                if not local_path.exists():
                                    self._log(
                                        f"Row {idx + 2}: image file not found -> {local_path}"
                                    )
                                    continue
                                try:
                                    encoded = base64.b64encode(local_path.read_bytes()).decode("ascii")
                                    one["attachment"] = encoded
                                    one["filename"] = local_path.name
                                except Exception as exc:
                                    self._log(
                                        f"Row {idx + 2}: cannot read image {local_path.name} ({exc})"
                                    )
                                    continue

                            alt = img.get("alt", "").strip()
                            if alt:
                                one["alt"] = alt
                            images_payload.append(one)

                        if images_payload:
                            prod["images"] = images_payload

                    selected_has_image_fields = any(
                        re.match(r"^images\.\d+\.(src|alt)$", h) for h in selected_cols
                    )

                    # Fallback: if image fields are selected but no usable image from columns,
                    # upload local images by SKU file name.
                    if selected_has_image_fields and "images" not in prod:
                        sku = rv("variants.0.sku") or rv("sku") or DEFAULT_SKU
                        images_payload = self._build_images_payload_from_folder(sku)
                        if images_payload:
                            prod["images"] = images_payload

                    if len(prod) == 1:
                        skip_count += 1
                        self._log(f"Row {idx + 2}  ID {product_id}: skip (no selected fields with value)")
                        save_session({"file": str(file_path), "pointer": idx + 1, "total": total})
                        self._prog["value"] = idx + 1
                        self._stats.set(
                            f"Row {idx + 2} / {total + 1}   ✓ {ok_count}   ✗ {fail_count}   - {skip_count}"
                        )
                        time.sleep(0.3)
                        continue

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
                        f"Row {idx + 2} / {total + 1}   ✓ {ok_count}   ✗ {fail_count}   - {skip_count}"
                    )
                    time.sleep(0.5)   # ~2 req/s — stay well under Shopify's 2 req/s limit

                # Done
                self._log(f"Upload complete — Success: {ok_count}, Failed: {fail_count}, Skipped: {skip_count}")
                self._app.set_status(f"Upload done — {ok_count} ok, {fail_count} failed, {skip_count} skipped")
                self._app.refresh_live_database()
                clear_session()
                self._cont_btn.config(state="disabled")
                self._stats.set(f"Finished — {ok_count} ok, {fail_count} failed, {skip_count} skipped")
                messagebox.showinfo(
                    "Upload Complete",
                    f"Done!\n\nSuccess: {ok_count}\nFailed:  {fail_count}\nSkipped: {skip_count}",
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
        if self._app.confirm_danger("Clear Session", "Clear the saved upload session?"):
            clear_session()
            self._cont_btn.config(state="disabled")
            self._stats.set("")
            self._log("Session cleared.")
