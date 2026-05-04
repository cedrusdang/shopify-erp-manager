"""Image download/upload tools for Shopify products."""

from __future__ import annotations

import base64
import re
import threading
import time
from urllib.parse import urlparse
from pathlib import Path
from tkinter import scrolledtext
import tkinter as tk
from tkinter import ttk, messagebox

import openpyxl
import requests

from ..api import update_product_api
from ..constants import DATABASE_FILE, DEFAULT_SKU, IMAGE_DIR


class ImagesUploadTab(ttk.Frame):
    def __init__(self, parent: ttk.Notebook, app):
        super().__init__(parent)
        self._app = app
        self._running = False
        self._headers: list[str] = []
        self._folder_item_paths: dict[str, Path] = {}
        self._field_vars: dict[str, tk.BooleanVar] = {}
        self._build()

    def _build(self) -> None:
        ttk.Label(
            self,
            text="Image Download Upload — download / upload / scan / delete by SKU",
            font=("Segoe UI", 10, "bold"),
            foreground="#0f6b45",
        ).pack(anchor=tk.W, padx=10, pady=(10, 6))

        info = ttk.LabelFrame(self, text=" Rules ", padding=8)
        info.pack(fill=tk.X, padx=8, pady=4)
        ttk.Label(
            info,
            text=(
                f"• Database file: {DATABASE_FILE}\n"
                f"• Image folder: {IMAGE_DIR}\n"
                "• Download: choose image URL field(s) from DB.\n"
                "• Upload mode 1: local files with SKU prefix are sent to Shopify.\n"
                "• Upload mode 2: send image URLs directly from DB fields (no local pre-download).\n"
                "• A text manifest image_sources.txt is written in image folder."
            ),
            justify=tk.LEFT,
            foreground="#444",
            font=("Segoe UI", 9),
        ).pack(anchor=tk.W)

        options = ttk.LabelFrame(self, text=" Shared Options (Download + Upload) ", padding=8)
        options.pack(fill=tk.X, padx=8, pady=(4, 2))

        sku_row = ttk.Frame(options)
        sku_row.pack(fill=tk.X, pady=(0, 4))
        ttk.Label(sku_row, text="SKU Scope:").pack(side=tk.LEFT)
        self._sku_all = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            sku_row,
            text="All",
            variable=self._sku_all,
            command=self._sync_sku_mode,
        ).pack(side=tk.LEFT, padx=(6, 8))
        ttk.Label(sku_row, text="SKU:").pack(side=tk.LEFT)
        self._sku_pick = tk.StringVar(value="")
        _sku_style = ttk.Style()
        _sku_style.map(
            "Sku.TCombobox",
            fieldbackground=[("disabled", "#f0f0f0"), ("readonly", "white")],
            foreground=[("disabled", "#aaaaaa"), ("readonly", "#000000")],
        )
        self._sku_combo = ttk.Combobox(sku_row, textvariable=self._sku_pick, state="disabled", style="Sku.TCombobox", width=36)
        self._sku_combo.pack(side=tk.LEFT, padx=(6, 6), fill=tk.X, expand=True)
        self._sku_combo.bind("<<ComboboxSelected>>", lambda _e: self._on_sku_changed())

        field_row = ttk.Frame(options)
        field_row.pack(fill=tk.X, pady=(4, 0))
        ttk.Label(field_row, text="Image Fields:").pack(side=tk.LEFT, anchor=tk.NW, pady=3)
        self._field_frame = ttk.Frame(field_row)
        self._field_frame.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(6, 0))
        ttk.Button(field_row, text="Refresh Fields", command=self._refresh_fields).pack(side=tk.RIGHT, padx=(4, 0))

        btns = ttk.Frame(self)
        btns.pack(fill=tk.X, padx=8, pady=4)
        ttk.Button(
            btns,
            text="Download Images",
            style="Primary.TButton",
            command=self._start_download_images,
        ).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(
            btns,
            text="Upload Images by SKU",
            style="Primary.TButton",
            command=self._start,
        ).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(btns, text="Scan Folder Coverage", command=self._scan_folder_coverage).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(btns, text="Delete Selected SKU Images", command=self._delete_selected_images).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(btns, text="Open Image Folder", command=self._open_folder).pack(side=tk.LEFT)

        self._stats = tk.StringVar(value="")
        ttk.Label(self, textvariable=self._stats, foreground="#333").pack(anchor=tk.W, padx=10, pady=(0, 4))

        self._prog = ttk.Progressbar(self, mode="determinate")
        self._prog.pack(fill=tk.X, padx=8, pady=(0, 6))

        ttk.Label(self, text="Folder Coverage (from DB rows):", font=("Segoe UI", 9, "bold")).pack(anchor=tk.W, padx=8)
        table_wrap = ttk.Frame(self)
        table_wrap.pack(fill=tk.BOTH, expand=False, padx=8, pady=(2, 6))
        self._tree = ttk.Treeview(
            table_wrap,
            columns=("id", "sku", "status", "files", "urls"),
            show="headings",
            height=8,
        )
        self._tree.heading("id", text="Product ID")
        self._tree.heading("sku", text="SKU")
        self._tree.heading("status", text="Folder Status")
        self._tree.heading("files", text="Local Files")
        self._tree.heading("urls", text="URL Count")
        self._tree.column("id", width=120, anchor=tk.W)
        self._tree.column("sku", width=180, anchor=tk.W)
        self._tree.column("status", width=120, anchor=tk.CENTER)
        self._tree.column("files", width=90, anchor=tk.CENTER)
        self._tree.column("urls", width=90, anchor=tk.CENTER)
        ysb = ttk.Scrollbar(table_wrap, orient=tk.VERTICAL, command=self._tree.yview)
        self._tree.configure(yscrollcommand=ysb.set)
        self._tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        ysb.pack(side=tk.RIGHT, fill=tk.Y)

        ttk.Label(self, text="Scanned Image Folders (double-click to open):", font=("Segoe UI", 9, "bold")).pack(anchor=tk.W, padx=8)
        folder_wrap = ttk.Frame(self)
        folder_wrap.pack(fill=tk.BOTH, expand=False, padx=8, pady=(2, 6))
        self._folder_tree = ttk.Treeview(
            folder_wrap,
            columns=("folder", "status", "files"),
            show="headings",
            height=5,
        )
        self._folder_tree.heading("folder", text="Folder")
        self._folder_tree.heading("status", text="Status")
        self._folder_tree.heading("files", text="File Count")
        self._folder_tree.column("folder", width=420, anchor=tk.W)
        self._folder_tree.column("status", width=120, anchor=tk.CENTER)
        self._folder_tree.column("files", width=90, anchor=tk.CENTER)
        fysb = ttk.Scrollbar(folder_wrap, orient=tk.VERTICAL, command=self._folder_tree.yview)
        self._folder_tree.configure(yscrollcommand=fysb.set)
        self._folder_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        fysb.pack(side=tk.RIGHT, fill=tk.Y)
        self._folder_tree.bind("<Double-1>", lambda _e: self._open_selected_folder())

        folder_btns = ttk.Frame(self)
        folder_btns.pack(fill=tk.X, padx=8, pady=(0, 4))
        ttk.Button(folder_btns, text="Refresh Folder List", command=self._refresh_folder_list).pack(side=tk.LEFT)
        ttk.Button(folder_btns, text="Open Selected Folder", command=self._open_selected_folder).pack(side=tk.LEFT, padx=(6, 0))

        ttk.Label(self, text="Image Download Upload Log:", font=("Segoe UI", 9, "bold")).pack(anchor=tk.W, padx=8)
        self._log_box = scrolledtext.ScrolledText(self, state="disabled", font=("Consolas", 8))
        self._log_box.pack(fill=tk.BOTH, expand=True, padx=8, pady=4)

        self._refresh_fields()
        self._sync_sku_mode()
        self._refresh_folder_list()

    def _log(self, msg: str) -> None:
        self._app.log(self._log_box, msg)

    def _safe_sku(self, value: str) -> str:
        sku = re.sub(r"[^A-Za-z0-9._-]+", "_", (value or "").strip())
        return sku[:80] or DEFAULT_SKU

    def _field_suffix(self, field_name: str) -> str:
        m = re.match(r"^images\.(\d+)\.src$", field_name)
        if m:
            return f"img_{m.group(1)}"
        clean = re.sub(r"[^A-Za-z0-9._-]+", "_", (field_name or "").strip())
        return clean[:40] or "img"

    def _field_folder_name(self, field_name: str) -> str:
        clean = re.sub(r"[^A-Za-z0-9._-]+", "_", (field_name or "").strip())
        return clean[:80] or "images"

    def _sku_files(self, sku: str) -> list[Path]:
        folder = Path(IMAGE_DIR)
        if not folder.exists():
            return []
        prefix = self._safe_sku(sku)
        return sorted([p for p in folder.rglob(f"{prefix}*.*") if p.is_file()])

    def _sku_files_for_field(self, sku: str, field_name: str) -> list[Path]:
        field = (field_name or "").strip()
        if not field:
            return []
        root = Path(IMAGE_DIR)
        field_folder = root / self._field_folder_name(field)
        if not field_folder.exists():
            return []
        prefix = self._safe_sku(sku)
        suffix = self._field_suffix(field)
        return sorted([p for p in field_folder.glob(f"{prefix}_{suffix}*.*") if p.is_file()])

    def _image_payload_for_sku(self, sku: str, field_name: str | None = None) -> list[dict]:
        files = self._sku_files_for_field(sku, field_name or "") if field_name else self._sku_files(sku)
        payload = []
        for p in files:
            try:
                encoded = base64.b64encode(p.read_bytes()).decode("ascii")
                payload.append({"attachment": encoded, "filename": p.name})
            except Exception:
                continue
        return payload

    def _load_db(self) -> tuple[list[str], list[tuple]]:
        db = Path(DATABASE_FILE)
        if not db.exists():
            raise FileNotFoundError(f"Cannot find {DATABASE_FILE}")
        wb = None
        try:
            wb = openpyxl.load_workbook(db, read_only=True, data_only=True)
            ws = wb.active
            rows = list(ws.iter_rows(values_only=True))
            if not rows:
                return [], []
            headers = [str(h or "").strip() for h in rows[0]]
            return headers, rows[1:]
        finally:
            if wb is not None:
                try:
                    wb.close()
                except Exception:
                    pass

    def _image_src_fields(self, headers: list[str]) -> list[str]:
        out: list[str] = []
        for h in headers:
            if re.match(r"^images\.\d+\.src$", h):
                out.append(h)
            elif "image" in h.lower() and h.lower().endswith(".src"):
                out.append(h)
        return out

    def _sync_sku_mode(self) -> None:
        if self._sku_all.get():
            self._sku_combo.configure(state="disabled")
        else:
            self._sku_combo.configure(state="readonly")
        self._highlight_selected_sku_row()

    def _on_sku_changed(self) -> None:
        self._highlight_selected_sku_row()

    def _highlight_selected_sku_row(self) -> None:
        target_sku = self._selected_sku()
        if not target_sku:
            self._tree.selection_remove(self._tree.selection())
            return

        matched_iid = None
        for iid in self._tree.get_children():
            vals = self._tree.item(iid, "values")
            sku_val = str(vals[1]).strip() if len(vals) > 1 else ""
            if sku_val == target_sku:
                matched_iid = iid
                break

        if matched_iid is not None:
            self._tree.selection_set(matched_iid)
            self._tree.focus(matched_iid)
            self._tree.see(matched_iid)

    def _on_field_changed(self) -> None:
        self._refresh_folder_list()

    def _refresh_sku_candidates(self, headers: list[str], data_rows: list[tuple]) -> None:
        sku_idx = headers.index("variants.0.sku") if "variants.0.sku" in headers else -1
        if sku_idx < 0:
            self._sku_combo["values"] = []
            self._sku_pick.set("")
            return
        skus: list[str] = []
        seen: set[str] = set()
        for row in data_rows:
            if sku_idx >= len(row) or row[sku_idx] in (None, ""):
                continue
            sku = str(row[sku_idx]).strip()
            if not sku or sku in seen:
                continue
            seen.add(sku)
            skus.append(sku)
        self._sku_combo["values"] = skus
        if skus and self._sku_pick.get() not in skus:
            self._sku_pick.set(skus[0])

    def _selected_sku(self) -> str | None:
        if self._sku_all.get():
            return None
        sku = self._sku_pick.get().strip()
        return sku or None

    def _refresh_fields(self) -> None:
        try:
            headers, data_rows = self._load_db()
        except Exception as exc:
            self._log(f"Field refresh error: {exc}")
            return
        self._headers = headers
        fields = self._image_src_fields(headers)

        # Rebuild field checkboxes — preserve previous checked state
        prev_checked = {f for f, v in self._field_vars.items() if v.get()}
        for w in self._field_frame.winfo_children():
            w.destroy()
        self._field_vars.clear()
        if fields:
            for f in fields:
                var = tk.BooleanVar(value=(f in prev_checked) if prev_checked else True)
                self._field_vars[f] = var
                ttk.Checkbutton(
                    self._field_frame, text=f, variable=var,
                    command=self._on_field_changed,
                ).pack(side=tk.LEFT, padx=(0, 8))
        else:
            ttk.Label(self._field_frame, text="No image fields found in DB", foreground="#888").pack(side=tk.LEFT)

        self._refresh_sku_candidates(headers, data_rows)
        self._refresh_folder_list()

    def _selected_image_fields(self, headers: list[str]) -> list[str]:
        all_fields = self._image_src_fields(headers)
        if self._field_vars:
            return [f for f in all_fields if self._field_vars.get(f) and self._field_vars[f].get()]
        return all_fields

    def _row_image_urls(self, row: tuple, headers: list[str], src_fields: list[str]) -> list[str]:
        urls: list[str] = []
        for f in src_fields:
            try:
                fi = headers.index(f)
            except ValueError:
                continue
            if fi < len(row) and row[fi] not in (None, ""):
                url = str(row[fi]).strip()
                if url.lower().startswith("http://") or url.lower().startswith("https://"):
                    urls.append(url)
        return urls

    def _write_manifest(self, lines: list[str]) -> Path:
        folder = Path(IMAGE_DIR)
        folder.mkdir(exist_ok=True)
        manifest = folder / "image_sources.txt"
        text = "filename\tproduct_id\tsku\tfield\tsource_url\n" + "\n".join(lines)
        manifest.write_text(text + "\n", encoding="utf-8")
        return manifest

    def _refresh_folder_list(self) -> None:
        root = Path(IMAGE_DIR)
        root.mkdir(exist_ok=True)

        for item in self._folder_tree.get_children():
            self._folder_tree.delete(item)
        self._folder_item_paths.clear()

        paths: list[Path] = [root]
        existing_subfolders = sorted([p for p in root.iterdir() if p.is_dir()])
        paths.extend(existing_subfolders)

        if self._headers:
            for field in self._selected_image_fields(self._headers):
                folder_name = self._field_folder_name(field)
                p = root / folder_name
                if p not in paths:
                    paths.append(p)

        seen: set[Path] = set()
        ordered_paths: list[Path] = []
        for p in paths:
            if p in seen:
                continue
            seen.add(p)
            ordered_paths.append(p)

        for idx, p in enumerate(ordered_paths, start=1):
            if p == root:
                label = "."
            else:
                label = str(p.relative_to(root)).replace("\\", "/")
            exists = p.exists()
            file_count = len([f for f in p.iterdir() if f.is_file()]) if exists else 0
            status = "HAS" if exists else "NOT DOWNLOADED YET"
            iid = f"folder-{idx}"
            self._folder_item_paths[iid] = p
            self._folder_tree.insert("", tk.END, iid=iid, values=(label, status, str(file_count)))

    def _open_selected_folder(self) -> None:
        sel = self._folder_tree.selection()
        if not sel:
            messagebox.showwarning("No Selection", "Select a folder in list first.", parent=self)
            return
        path = self._folder_item_paths.get(sel[0])
        if path is None:
            return
        path.mkdir(parents=True, exist_ok=True)
        self._app.set_status(f"Folder ready: {path.resolve()}")
        try:
            import os
            os.startfile(str(path.resolve()))
        except Exception:
            messagebox.showinfo("Folder", f"Folder: {path.resolve()}", parent=self)

    def _start_download_images(self) -> None:
        if self._running:
            messagebox.showwarning("Busy", "Another image task is running.", parent=self)
            return

        if not self._app.confirm_danger(
            "Confirm Images Download",
            "Download images from selected DB image field(s) into local folder now?",
        ):
            return

        self._running = True

        def task():
            self._app.start_prog("indeterminate")
            self._log("Starting image download from DB fields…")
            ok_count = fail_count = skip_count = 0
            manifest_lines: list[str] = []

            try:
                headers, data_rows = self._load_db()
                if not headers:
                    self._log("Database is empty.")
                    return

                id_idx = headers.index("id") if "id" in headers else -1
                sku_idx = headers.index("variants.0.sku") if "variants.0.sku" in headers else -1
                src_fields = self._selected_image_fields(headers)
                if not src_fields:
                    self._log("No image src fields selected/found.")
                    return

                selected_sku = self._selected_sku()
                if selected_sku:
                    self._log(f"Download scope: SKU '{selected_sku}'")
                else:
                    self._log("Download scope: ALL SKU")

                field_indices = [headers.index(f) for f in src_fields]
                rows_to_process = []
                for row in data_rows:
                    sku_val = ""
                    if sku_idx >= 0 and sku_idx < len(row) and row[sku_idx] not in (None, ""):
                        sku_val = str(row[sku_idx]).strip()
                    if selected_sku and sku_val != selected_sku:
                        continue
                    rows_to_process.append(row)

                total = len(rows_to_process)
                if total == 0:
                    self._log("No rows matched selected SKU scope.")
                    return
                self._prog.configure(maximum=max(total, 1), value=0)
                self._app.start_prog("determinate")

                root_folder = Path(IMAGE_DIR)
                root_folder.mkdir(exist_ok=True)

                target_field = src_fields[0]
                target_folder = root_folder / self._field_folder_name(target_field)
                target_folder.mkdir(parents=True, exist_ok=True)
                existing_files = [p for p in target_folder.iterdir() if p.is_file()]
                if existing_files:
                    choice = messagebox.askyesnocancel(
                        "Existing Downloaded Images",
                        f"Folder already has {len(existing_files)} file(s):\n{target_folder.resolve()}\n\n"
                        "Yes = Replace existing files while downloading\n"
                        "No = Delete existing files first, then download\n"
                        "Cancel = Abort",
                        parent=self,
                    )
                    if choice is None:
                        self._log("Download cancelled by user (existing files prompt).")
                        return
                    if choice is False:
                        removed = 0
                        for p in existing_files:
                            try:
                                p.unlink(missing_ok=True)
                                removed += 1
                            except Exception:
                                pass
                        self._log(f"Deleted {removed} existing file(s) in target folder before download.")
                    else:
                        self._log("Existing files will be replaced if names match.")

                for i, row in enumerate(rows_to_process, start=1):
                    product_id = ""
                    if id_idx >= 0 and id_idx < len(row) and row[id_idx] not in (None, ""):
                        product_id = str(row[id_idx]).strip()

                    sku = ""
                    if sku_idx >= 0 and sku_idx < len(row) and row[sku_idx] not in (None, ""):
                        sku = str(row[sku_idx]).strip()
                    if not sku:
                        sku = DEFAULT_SKU
                    safe_sku = self._safe_sku(sku)

                    row_urls: list[tuple[str, str]] = []
                    for fi, f in zip(field_indices, src_fields):
                        if fi < len(row) and row[fi] not in (None, ""):
                            url = str(row[fi]).strip()
                            if url.lower().startswith("http://") or url.lower().startswith("https://"):
                                row_urls.append((f, url))

                    if not row_urls:
                        skip_count += 1
                        self._prog["value"] = i
                        continue

                    for field_name, url in row_urls:
                        try:
                            ext = Path(urlparse(url).path).suffix.lower()
                            if ext not in {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".tif", ".tiff"}:
                                ext = ".jpg"
                            field_folder = root_folder / self._field_folder_name(field_name)
                            field_folder.mkdir(parents=True, exist_ok=True)
                            suffix = self._field_suffix(field_name)
                            file_name = f"{safe_sku}_{suffix}{ext}"
                            target = field_folder / file_name
                            file_name = str(target.relative_to(root_folder)).replace("\\", "/")
                            resp = requests.get(url, timeout=30)
                            resp.raise_for_status()
                            target.write_bytes(resp.content)
                            manifest_lines.append(
                                f"{file_name}\t{product_id}\t{sku}\t{field_name}\t{url}"
                            )
                            ok_count += 1
                        except Exception as exc:
                            fail_count += 1
                            self._log(f"Download fail ID {product_id} SKU {sku}: {exc}")

                    self._prog["value"] = i
                    self._stats.set(
                        f"Row {i}/{total}  DOWN_OK:{ok_count}  DOWN_FAIL:{fail_count}  SKIP:{skip_count}"
                    )

                manifest = self._write_manifest(manifest_lines)
                self._log(f"Manifest written: {manifest}")
                self._log(f"Download done. OK:{ok_count} FAIL:{fail_count} SKIP:{skip_count}")
                self._app.set_status("Images download completed")
                self._scan_folder_coverage()
                self._refresh_folder_list()
            except Exception as exc:
                self._log(f"ERROR: {exc}")
                self._app.set_status("Images download failed")
                messagebox.showerror("Images Download Error", str(exc), parent=self)
            finally:
                self._running = False
                self._app.stop_prog()

        threading.Thread(target=task, daemon=True).start()

    def _scan_folder_coverage(self) -> None:
        try:
            headers, data_rows = self._load_db()
        except Exception as exc:
            self._log(f"Scan error: {exc}")
            return

        for item in self._tree.get_children():
            self._tree.delete(item)

        if not headers:
            self._stats.set("Database is empty")
            return

        id_idx = headers.index("id") if "id" in headers else -1
        sku_idx = headers.index("variants.0.sku") if "variants.0.sku" in headers else -1
        src_fields = self._selected_image_fields(headers)
        src_idx = [headers.index(f) for f in src_fields]

        has_count = 0
        miss_count = 0
        for i, row in enumerate(data_rows, start=1):
            product_id = str(row[id_idx]).strip() if id_idx >= 0 and id_idx < len(row) and row[id_idx] not in (None, "") else ""
            sku = str(row[sku_idx]).strip() if sku_idx >= 0 and sku_idx < len(row) and row[sku_idx] not in (None, "") else DEFAULT_SKU
            files = self._sku_files_for_field(sku, src_fields[0]) if src_fields else []
            url_count = 0
            for fi in src_idx:
                if fi < len(row) and row[fi] not in (None, ""):
                    u = str(row[fi]).strip().lower()
                    if u.startswith("http://") or u.startswith("https://"):
                        url_count += 1
            status = "HAS" if files else "MISSING"
            if files:
                has_count += 1
            else:
                miss_count += 1
            self._tree.insert(
                "",
                tk.END,
                iid=str(i),
                values=(product_id, sku, status, str(len(files)), str(url_count)),
            )

        self._stats.set(f"Coverage: HAS {has_count} | MISSING {miss_count} | Rows {len(data_rows)}")
        self._log(f"Coverage scan done: HAS {has_count}, MISSING {miss_count}, rows {len(data_rows)}")
        self._highlight_selected_sku_row()
        self._refresh_folder_list()

    def _delete_selected_images(self) -> None:
        sel = self._tree.selection()
        if not sel:
            messagebox.showwarning("No Selection", "Select row(s) in coverage table first.", parent=self)
            return

        if not self._app.confirm_danger(
            "Delete Local Images",
            f"Delete local image files for {len(sel)} selected SKU row(s)?",
        ):
            return

        removed = 0
        for iid in sel:
            vals = self._tree.item(iid, "values")
            sku = str(vals[1]) if len(vals) > 1 else ""
            for f in self._sku_files(sku):
                try:
                    f.unlink(missing_ok=True)
                    removed += 1
                except Exception:
                    pass

        self._log(f"Deleted {removed} local image file(s) from selected rows.")
        self._scan_folder_coverage()
        self._refresh_folder_list()

    def _open_folder(self) -> None:
        folder = Path(IMAGE_DIR)
        folder.mkdir(exist_ok=True)
        self._app.set_status(f"Image folder ready: {folder.resolve()}")
        try:
            import os
            os.startfile(str(folder.resolve()))
        except Exception:
            messagebox.showinfo("Folder", f"Image folder: {folder.resolve()}", parent=self)

    def _start(self) -> None:
        if self._running:
            messagebox.showwarning("Busy", "Another image task is running.", parent=self)
            return

        store, token = self._app.get_conn()
        if not store:
            return

        db = Path(DATABASE_FILE)
        if not db.exists():
            messagebox.showwarning("Database Missing", f"Cannot find {DATABASE_FILE}", parent=self)
            return

        if not self._app.confirm_danger(
            "Confirm Images Upload",
            "Upload local images by SKU to Shopify now?",
        ):
            return

        self._running = True

        def task():
            self._app.start_prog("indeterminate")
            self._log("Starting images upload by SKU…")
            ok_count = fail_count = skip_count = 0
            wb = None

            try:
                wb = openpyxl.load_workbook(db, read_only=True, data_only=True)
                ws = wb.active
                rows = list(ws.iter_rows(values_only=True))
                if not rows:
                    self._log("Database is empty.")
                    return

                headers = [str(h or "").strip() for h in rows[0]]
                data_rows = rows[1:]
                total = len(data_rows)
                self._prog.configure(maximum=max(total, 1), value=0)
                self._app.start_prog("determinate")

                if "id" not in headers:
                    self._log("Missing required column: id")
                    return

                id_idx = headers.index("id")
                sku_idx = headers.index("variants.0.sku") if "variants.0.sku" in headers else -1
                src_fields = self._selected_image_fields(headers)
                selected_sku = self._selected_sku()

                for i, row in enumerate(data_rows, start=1):
                    product_id = str(row[id_idx]).strip() if id_idx < len(row) and row[id_idx] not in (None, "") else ""
                    if not product_id:
                        skip_count += 1
                        continue

                    sku = ""
                    if sku_idx >= 0 and sku_idx < len(row) and row[sku_idx] not in (None, ""):
                        sku = str(row[sku_idx]).strip()
                    if not sku:
                        sku = DEFAULT_SKU
                    if selected_sku and sku != selected_sku:
                        skip_count += 1
                        self._prog["value"] = i
                        continue

                    images = self._image_payload_for_sku(sku, src_fields[0] if src_fields else None)

                    if not images:
                        skip_count += 1
                        self._log(f"Skip ID {product_id}: no image files for SKU '{sku}'")
                    else:
                        ok, code, err = update_product_api(
                            store,
                            token,
                            product_id,
                            {"product": {"id": product_id, "images": images}},
                        )
                        if ok:
                            ok_count += 1
                            self._log(f"OK ID {product_id}: uploaded {len(images)} images (SKU {sku})")
                        else:
                            fail_count += 1
                            self._log(f"FAIL ID {product_id}: {code} {err}")

                    self._prog["value"] = i
                    self._stats.set(
                        f"Row {i}/{total}  OK:{ok_count}  FAIL:{fail_count}  SKIP:{skip_count}"
                    )
                    time.sleep(0.35)

                self._log(f"Done. OK:{ok_count} FAIL:{fail_count} SKIP:{skip_count}")
                self._app.set_status("Images upload completed")
                self._scan_folder_coverage()
            except Exception as exc:
                self._log(f"ERROR: {exc}")
                self._app.set_status("Images upload failed")
                messagebox.showerror("Images Upload Error", str(exc), parent=self)
            finally:
                if wb is not None:
                    try:
                        wb.close()
                    except Exception:
                        pass
                self._running = False
                self._app.stop_prog()

        threading.Thread(target=task, daemon=True).start()
