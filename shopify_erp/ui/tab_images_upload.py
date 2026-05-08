"""Image upload tools for Shopify products."""

from __future__ import annotations

import base64
import logging
import re
import threading
import time
from pathlib import Path
from tkinter import scrolledtext, filedialog
import tkinter as tk
from tkinter import ttk, messagebox

import openpyxl
import requests

from ..api import update_product_api, test_connection
from ..constants import DATABASE_FILE, DEFAULT_SKU, IMAGE_DIR

logger = logging.getLogger(__name__)

# Common image extensions
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}


class ImagesUploadTab(ttk.Frame):
    """Image upload tool - upload local images to Shopify product variants."""

    def __init__(self, parent: ttk.Notebook, app):
        super().__init__(parent)
        self._app = app
        self._running = False
        self._headers: list[str] = []
        self._sku_mode = tk.StringVar(value="all")
        self._selected_folder = tk.StringVar(value="")
        self._image_suffix = tk.StringVar(value="")
        self._build()

    def _build(self) -> None:
        ttk.Label(
            self,
            text="Image Upload — upload local images to Shopify product variants",
            font=("Segoe UI", 10, "bold"),
            foreground="#0f6b45",
        ).pack(anchor=tk.W, padx=10, pady=(10, 6))

        info = ttk.LabelFrame(self, text=" How It Works ", padding=8)
        info.pack(fill=tk.X, padx=8, pady=4)
        ttk.Label(
            info,
            text=(
                "1. Select a folder containing image files.\n"
                "2. Specify the image suffix pattern (e.g., '_main', '_alt1').\n"
                "3. Images must be named: {SKU}{suffix}.{ext} (e.g., ABC123_main.jpg).\n"
                "4. Choose SKU scope: All, Single, or Group.\n"
                "5. Click 'Upload Images' to add images to Shopify products.\n"
                "6. Images are uploaded as base64 attachments."
            ),
            justify=tk.LEFT,
            foreground="#444",
            font=("Segoe UI", 9),
        ).pack(anchor=tk.W)

        options = ttk.LabelFrame(self, text=" Upload Options ", padding=8)
        options.pack(fill=tk.X, padx=8, pady=(4, 2))

        # Folder selection
        folder_row = ttk.Frame(options)
        folder_row.pack(fill=tk.X, pady=(0, 6))
        ttk.Label(folder_row, text="Image Folder:").pack(side=tk.LEFT)
        ttk.Entry(folder_row, textvariable=self._selected_folder, state="readonly").pack(side=tk.LEFT, padx=(6, 6), fill=tk.X, expand=True)
        ttk.Button(folder_row, text="Browse...", command=self._select_folder).pack(side=tk.LEFT)

        # Image suffix
        suffix_row = ttk.Frame(options)
        suffix_row.pack(fill=tk.X, pady=(0, 6))
        ttk.Label(suffix_row, text="Image Suffix Pattern:").pack(side=tk.LEFT)
        self._suffix_entry = ttk.Entry(suffix_row, textvariable=self._image_suffix)
        self._suffix_entry.pack(side=tk.LEFT, padx=(6, 0), fill=tk.X, expand=True)
        ttk.Label(suffix_row, text="e.g. _main, _alt1, etc.", foreground="#999", font=("Segoe UI", 8)).pack(side=tk.LEFT, padx=(4, 0))

        # SKU scope
        sku_row = ttk.Frame(options)
        sku_row.pack(fill=tk.X, pady=(0, 2))
        ttk.Label(sku_row, text="SKU Scope:").pack(side=tk.LEFT)
        ttk.Radiobutton(sku_row, text="All", value="all", variable=self._sku_mode, command=self._sync_sku_mode).pack(side=tk.LEFT, padx=(6, 8))
        ttk.Radiobutton(sku_row, text="Single", value="single", variable=self._sku_mode, command=self._sync_sku_mode).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Radiobutton(sku_row, text="Group", value="group", variable=self._sku_mode, command=self._sync_sku_mode).pack(side=tk.LEFT, padx=(0, 8))

        single_sku_row = ttk.Frame(options)
        single_sku_row.pack(fill=tk.X, pady=(0, 2))
        ttk.Label(single_sku_row, text="Single SKU:").pack(side=tk.LEFT)
        self._sku_pick = tk.StringVar(value="")
        self._sku_combo = ttk.Combobox(single_sku_row, textvariable=self._sku_pick, state="disabled", width=36)
        self._sku_combo.pack(side=tk.LEFT, padx=(6, 0), fill=tk.X, expand=True)

        group_sku_row = ttk.Frame(options)
        group_sku_row.pack(fill=tk.X, pady=(0, 4))
        ttk.Label(group_sku_row, text="Group SKU (comma/newline):").pack(side=tk.LEFT)
        self._sku_group = tk.StringVar(value="")
        self._sku_group_entry = ttk.Entry(group_sku_row, textvariable=self._sku_group, state="disabled")
        self._sku_group_entry.pack(side=tk.LEFT, padx=(6, 0), fill=tk.X, expand=True)

        # Upload button
        btns = ttk.Frame(self)
        btns.pack(fill=tk.X, padx=8, pady=4)
        ttk.Button(
            btns,
            text="Upload Images",
            style="Primary.TButton",
            command=self._start_upload_images,
        ).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(btns, text="Scan Folder", command=self._scan_available_images).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(btns, text="Open Folder", command=self._open_selected_folder).pack(side=tk.LEFT)

        self._stats = tk.StringVar(value="")
        ttk.Label(self, textvariable=self._stats, foreground="#333").pack(anchor=tk.W, padx=10, pady=(0, 4))

        self._prog = ttk.Progressbar(self, mode="determinate")
        self._prog.pack(fill=tk.X, padx=8, pady=(0, 6))

        # Available images tree
        ttk.Label(self, text="Available Images in Folder:", font=("Segoe UI", 9, "bold")).pack(anchor=tk.W, padx=8)
        tree_wrap = ttk.Frame(self)
        tree_wrap.pack(fill=tk.BOTH, expand=False, padx=8, pady=(2, 6))
        self._tree = ttk.Treeview(
            tree_wrap,
            columns=("filename", "size", "sku", "suffix"),
            show="headings",
            height=6,
        )
        self._tree.heading("filename", text="Filename")
        self._tree.heading("size", text="Size (KB)")
        self._tree.heading("sku", text="SKU")
        self._tree.heading("suffix", text="Suffix")
        self._tree.column("filename", width=280, anchor=tk.W)
        self._tree.column("size", width=80, anchor=tk.CENTER)
        self._tree.column("sku", width=120, anchor=tk.CENTER)
        self._tree.column("suffix", width=100, anchor=tk.CENTER)
        ysb = ttk.Scrollbar(tree_wrap, orient=tk.VERTICAL, command=self._tree.yview)
        self._tree.configure(yscrollcommand=ysb.set)
        self._tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        ysb.pack(side=tk.RIGHT, fill=tk.Y)

        # Log
        ttk.Label(self, text="Upload Log:", font=("Segoe UI", 9, "bold")).pack(anchor=tk.W, padx=8)
        self._log_box = scrolledtext.ScrolledText(self, state="disabled", font=("Consolas", 8))
        self._log_box.pack(fill=tk.BOTH, expand=True, padx=8, pady=4)

        self._sync_sku_mode()
        self._load_skus_from_db()

    def _log(self, msg: str) -> None:
        logger.info(f"[ImagesUploadTab] {msg}")
        try:
            self.after(0, lambda m=msg: self._app.log(self._log_box, m))
        except Exception:
            logger.debug("[ImagesUploadTab] UI log dispatch skipped", exc_info=True)

    def _ui_async(self, fn) -> None:
        try:
            self.after(0, fn)
        except Exception:
            logger.debug("[ImagesUploadTab] UI async dispatch failed", exc_info=True)

    def _sync_sku_mode(self) -> None:
        mode = self._sku_mode.get()
        if mode == "single":
            self._sku_combo.config(state="readonly")
            self._sku_group_entry.config(state="disabled")
        elif mode == "group":
            self._sku_combo.config(state="disabled")
            self._sku_group_entry.config(state="normal")
        else:  # all
            self._sku_combo.config(state="disabled")
            self._sku_group_entry.config(state="disabled")

    def _select_folder(self) -> None:
        folder = filedialog.askdirectory(title="Select Image Folder")
        if folder:
            self._selected_folder.set(folder)
            self._scan_available_images()

    def _open_selected_folder(self) -> None:
        folder = self._selected_folder.get().strip()
        if not folder:
            messagebox.showwarning("No Folder", "Please select an image folder first.", parent=self)
            return
        try:
            import subprocess
            import platform
            if platform.system() == "Windows":
                subprocess.Popen(["explorer", folder])
            elif platform.system() == "Darwin":
                subprocess.Popen(["open", folder])
            else:
                subprocess.Popen(["xdg-open", folder])
        except Exception as e:
            logger.exception("Failed to open folder")
            messagebox.showerror("Error", f"Could not open folder: {e}", parent=self)

    def _load_skus_from_db(self) -> None:
        """Load SKU list from database for single SKU selector."""
        try:
            wb = openpyxl.load_workbook(DATABASE_FILE, data_only=True)
            ws = wb.active
            skus = []
            for row in ws.iter_rows(min_row=2, values_only=True):
                sku = str(row[1]).strip() if len(row) > 1 and row[1] else ""
                if sku and sku != DEFAULT_SKU:
                    skus.append(sku)
            self._sku_combo["values"] = skus
            wb.close()
        except Exception as e:
            logger.exception("Failed to load SKUs from DB")
            self._log(f"Error loading SKUs: {e}")

    def _scan_available_images(self) -> None:
        """Scan folder and update tree with available images."""
        folder = self._selected_folder.get().strip()
        suffix = self._image_suffix.get().strip()

        self._tree.delete(*self._tree.get_children())

        if not folder:
            self._log("No folder selected.")
            return

        folder_path = Path(folder)
        if not folder_path.is_dir():
            self._log(f"Folder not found: {folder}")
            return

        self._log(f"Scanning folder: {folder}")

        try:
            images = []
            for file_path in folder_path.glob("*"):
                if file_path.is_file() and file_path.suffix.lower() in IMAGE_EXTENSIONS:
                    stem = file_path.stem
                    ext = file_path.suffix.lower()

                    # Try to extract SKU and suffix from filename
                    # Expected format: {sku}{suffix}.{ext} or just {sku}.{ext}
                    sku = None
                    img_suffix = ""

                    if suffix:
                        # If user specified suffix, look for {sku}{suffix}.{ext}
                        if stem.endswith(suffix):
                            sku = stem[: len(stem) - len(suffix)]
                            img_suffix = suffix
                    else:
                        # Just use filename as SKU
                        sku = stem
                        img_suffix = ""

                    if sku:
                        size_kb = file_path.stat().st_size / 1024
                        images.append((file_path.name, size_kb, sku, img_suffix))
                        self._tree.insert("", "end", values=(file_path.name, f"{size_kb:.1f}", sku, img_suffix))

            self._log(f"Found {len(images)} image(s) in folder.")
            self._stats.set(f"Available: {len(images)} image(s)")
        except Exception as e:
            logger.exception("Folder scan failed")
            self._log(f"Error scanning folder: {e}")

    def _selected_sku_set(self) -> set[str]:
        """Get set of selected SKUs based on mode."""
        mode = self._sku_mode.get()
        if mode == "single":
            sku = self._sku_pick.get().strip()
            return {sku} if sku else set()
        elif mode == "group":
            group_text = self._sku_group.get().strip()
            if not group_text:
                return set()
            # Split by comma or newline
            skus = re.split(r"[,\n]+", group_text)
            return {s.strip() for s in skus if s.strip()}
        else:  # all
            return set()  # Empty set means "all"

    def _start_upload_images(self) -> None:
        """Start upload process in background thread."""
        folder = self._selected_folder.get().strip()
        suffix = self._image_suffix.get().strip()

        if not folder:
            messagebox.showwarning("No Folder", "Please select an image folder.", parent=self)
            return

        if not Path(folder).is_dir():
            messagebox.showerror("Invalid Folder", f"Folder not found: {folder}", parent=self)
            return

        store, token = self._app.get_conn()
        if not store or not token:
            return

        # Confirm upload start
        sku_set = self._selected_sku_set()
        scope_desc = f"({len(sku_set)} SKUs)" if sku_set else "(all SKUs)"
        msg = f"Upload images from:\n{folder}\n\nSuffix: {suffix if suffix else '(none)'}\nScope: {scope_desc}\n\nProceed?"
        if not self._app.confirm("Confirm Image Upload", msg):
            return

        self._running = True
        self._app.start_prog("determinate", use_busy_cursor=False)
        self._log("Upload task started…")

        def task():
            try:
                self._run_upload_task(store, token, folder, suffix, sku_set)
            except Exception as exc:
                logger.exception("Upload task crashed")
                self._ui_async(lambda: self._app.stop_prog(clear_busy_cursor=False))
                self._ui_async(lambda: messagebox.showerror("Upload Error", str(exc), parent=self))
            finally:
                self._running = False

        thread = threading.Thread(target=task, daemon=True)
        thread.start()

    def _run_upload_task(self, store: str, token: str, folder: str, suffix: str, sku_set: set[str]) -> None:
        """Execute the upload task."""
        start_time = time.time()

        try:
            # Load database to get SKU->ID mapping
            self._log_step(1, "Loading product database")
            wb = openpyxl.load_workbook(DATABASE_FILE, data_only=True)
            ws = wb.active

            sku_to_id = {}
            for row in ws.iter_rows(min_row=2, values_only=True):
                if len(row) < 2:
                    continue
                prod_id = str(row[0]).strip() if row[0] else ""
                sku = str(row[1]).strip() if row[1] else ""
                if prod_id and sku and sku != DEFAULT_SKU:
                    sku_to_id[sku] = prod_id
            wb.close()
            self._log(f"Loaded {len(sku_to_id)} SKU→ID mappings from database")

            # Scan folder for images
            self._log_step(2, "Scanning image folder")
            folder_path = Path(folder)
            images_by_sku: dict[str, list[Path]] = {}

            for file_path in folder_path.glob("*"):
                if file_path.is_file() and file_path.suffix.lower() in IMAGE_EXTENSIONS:
                    stem = file_path.stem
                    sku = None
                    if suffix:
                        if stem.endswith(suffix):
                            sku = stem[: len(stem) - len(suffix)]
                    else:
                        sku = stem

                    if sku:
                        if sku not in images_by_sku:
                            images_by_sku[sku] = []
                        images_by_sku[sku].append(file_path)

            self._log(f"Found images for {len(images_by_sku)} SKU(s)")

            # Determine which SKUs to upload
            upload_skus = sku_set if sku_set else set(images_by_sku.keys())
            upload_skus = upload_skus & set(sku_to_id.keys())

            if not upload_skus:
                self._ui_async(lambda: self._log("No matching SKUs found in database."))
                self._ui_async(lambda: self._app.stop_prog(clear_busy_cursor=False))
                return

            self._log(f"Will upload to {len(upload_skus)} product(s)")

            # Upload images
            self._log_step(3, f"Uploading to {len(upload_skus)} product(s)")
            ok_count = 0
            fail_count = 0
            skip_count = 0

            for i, sku in enumerate(sorted(upload_skus)):
                if not self._running:
                    self._log("Upload cancelled by user")
                    break

                prod_id = sku_to_id[sku]
                sku_images = images_by_sku.get(sku, [])

                if not sku_images:
                    skip_count += 1
                    self._log(f"  [{i + 1}/{len(upload_skus)}] SKU {sku}: no images, skip")
                    continue

                for img_path in sku_images:
                    try:
                        # Read and encode image
                        with open(img_path, "rb") as f:
                            img_data = f.read()
                        attachment = base64.b64encode(img_data).decode("utf-8")

                        # Upload to Shopify
                        payload = {
                            "image": {
                                "attachment": attachment,
                                "alt": f"Product image: {sku}",
                            }
                        }

                        url = f"https://{store}/admin/api/2024-10/products/{prod_id}/images.json"
                        resp = requests.post(
                            url,
                            headers={"X-Shopify-Access-Token": token, "Content-Type": "application/json"},
                            json=payload,
                            timeout=45,
                        )

                        if resp.ok:
                            ok_count += 1
                            self._log(f"  [{i + 1}/{len(upload_skus)}] SKU {sku}: {img_path.name} ✓")
                        else:
                            fail_count += 1
                            error_msg = resp.text[:100] if resp.text else f"HTTP {resp.status_code}"
                            self._log(f"  [{i + 1}/{len(upload_skus)}] SKU {sku}: {img_path.name} ✗ ({error_msg})")

                    except Exception as e:
                        fail_count += 1
                        self._log(f"  [{i + 1}/{len(upload_skus)}] SKU {sku}: {img_path.name} ✗ ({e})")

                # Update progress
                progress = int((i + 1) / len(upload_skus) * 100)
                self._ui_async(lambda p=progress: self._app.set_prog_value(p, 100))

            # Done
            elapsed = time.time() - start_time
            self._log_step(4, f"Upload completed in {elapsed:.1f}s (ok={ok_count}, fail={fail_count}, skip={skip_count})")
            self._stats.set(f"Uploaded: {ok_count} images | Failed: {fail_count} | Skipped: {skip_count}")

            self._ui_async(lambda: self._app.stop_prog(clear_busy_cursor=False))
            self._ui_async(
                lambda: messagebox.showinfo(
                    "Upload Complete",
                    f"Uploaded: {ok_count}\nFailed: {fail_count}\nSkipped: {skip_count}\n\nTime: {elapsed:.1f}s",
                    parent=self,
                )
            )

        except Exception as exc:
            logger.exception("Upload task failed")
            self._ui_async(lambda: self._app.stop_prog(clear_busy_cursor=False))
            raise

    def _log_step(self, step_no: int, title: str, detail: str = "") -> None:
        if detail:
            self._log(f"[Step {step_no}] {title} — {detail}")
        else:
            self._log(f"[Step {step_no}] {title}")
