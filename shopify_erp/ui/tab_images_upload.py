"""Image upload tools for Shopify products."""

from __future__ import annotations

import base64
import json
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

from ..api import get_metafield_definition_type, update_product_api, upload_file_to_shopify_files
from ..constants import DATABASE_FILE, DEFAULT_SKU, IMAGE_DIR

logger = logging.getLogger(__name__)

# Common image extensions
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}
FOLDER_STATE_FILE = "image_upload_folder_state.json"


class ImagesUploadTab(ttk.Frame):
    """Image upload tool - upload local images to Shopify product variants."""

    def __init__(self, parent: ttk.Notebook, app):
        super().__init__(parent)
        self._app = app
        self._running = False
        self._headers: list[str] = []
        self._field_pick = tk.StringVar(value="")
        self._sku_mode = tk.StringVar(value="all")
        self._selected_folder = tk.StringVar(value=self._load_selected_folder())
        self._build()

    def _initial_image_folder(self) -> str:
        root = Path(IMAGE_DIR)
        if not root.is_absolute():
            root = Path.cwd() / root
        return str(root.resolve())

    def _folder_state_path(self) -> Path:
        return Path.cwd() / FOLDER_STATE_FILE

    def _load_selected_folder(self) -> str:
        default_folder = self._initial_image_folder()
        path = self._folder_state_path()
        if not path.exists():
            return default_folder
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            logger.exception("Failed to read folder state")
            return default_folder

        folder = str(data.get("selected_folder", "")).strip()
        return folder if folder else default_folder

    def _save_selected_folder(self, folder: str) -> None:
        payload = {"selected_folder": folder}
        path = self._folder_state_path()
        try:
            path.write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")
        except Exception:
            logger.exception("Failed to save folder state")

    def _set_selected_folder(self, folder: str) -> None:
        resolved = str(Path(folder).expanduser().resolve())
        self._selected_folder.set(resolved)
        self._save_selected_folder(resolved)

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
                "2. Local image filenames should use SKU only (e.g., ABC123.jpg).\n"
                "3. Target Field controls where the uploaded image is stored.\n"
                "4. Use variants.0.metafields... for SKU-specific images; use metafields... for shared product images.\n"
                "5. Metafield targets upload into Shopify Files and then write the resulting file URL/reference into the field.\n"
                "6. images.*.src adds to the product image gallery instead of writing a metafield.\n"
                "7. Choose SKU scope: All, Single, or Group.\n"
                "8. Click 'Upload Images' to upload and update the selected field."
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

        # Field selection
        field_row = ttk.Frame(options)
        field_row.pack(fill=tk.X, pady=(0, 6))
        ttk.Label(field_row, text="Target Field:").pack(side=tk.LEFT)
        self._field_combo = ttk.Combobox(field_row, textvariable=self._field_pick, state="readonly", width=42)
        self._field_combo.pack(side=tk.LEFT, padx=(6, 0), fill=tk.X, expand=True)
        ttk.Label(
            options,
            text=(
                "Note: this upload flow supports only 2 field shapes: images.0.src and "
                "metafields.custom.ecom_img_1. Metafield targets do not add to product gallery."
            ),
            foreground="#555",
            font=("Segoe UI", 8),
            justify=tk.LEFT,
        ).pack(anchor=tk.W, pady=(0, 6))

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
            columns=("filename", "size", "sku"),
            show="headings",
            height=6,
        )
        self._tree.heading("filename", text="Filename")
        self._tree.heading("size", text="Size (KB)")
        self._tree.heading("sku", text="SKU")
        self._tree.column("filename", width=280, anchor=tk.W)
        self._tree.column("size", width=80, anchor=tk.CENTER)
        self._tree.column("sku", width=120, anchor=tk.CENTER)
        ysb = ttk.Scrollbar(tree_wrap, orient=tk.VERTICAL, command=self._tree.yview)
        self._tree.configure(yscrollcommand=ysb.set)
        self._tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        ysb.pack(side=tk.RIGHT, fill=tk.Y)

        # Log
        ttk.Label(self, text="Upload Log:", font=("Segoe UI", 9, "bold")).pack(anchor=tk.W, padx=8)
        self._log_box = scrolledtext.ScrolledText(self, state="disabled", font=("Consolas", 8))
        self._log_box.pack(fill=tk.BOTH, expand=True, padx=8, pady=4)

        self._sync_sku_mode()
        self._load_field_options()
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

    def _image_root_dir(self) -> str:
        """Deprecated: use _initial_image_folder() instead."""
        return self._initial_image_folder()

    def _is_product_metafield_field(self, field_name: str) -> bool:
        return field_name.startswith("metafields.")

    def _is_variant_metafield_field(self, field_name: str) -> bool:
        return field_name.startswith("variants.0.metafields.")

    def _is_product_image_field(self, field_name: str) -> bool:
        return field_name.startswith("images.") and field_name.endswith(".src")

    def _is_supported_field(self, field_name: str) -> bool:
        return (
            self._is_product_metafield_field(field_name)
            or self._is_variant_metafield_field(field_name)
            or self._is_product_image_field(field_name)
        )

    def _build_field_update_payload(self, field_name: str, value: str, variant_id: str = "") -> dict | None:
        if self._is_product_metafield_field(field_name):
            parts = field_name.split(".", 2)
            if len(parts) != 3:
                return None
            _prefix, namespace, key = parts
            return {"product": {"metafields": {namespace: {key: value}}}}

        if self._is_variant_metafield_field(field_name):
            parts = field_name.split(".", 4)
            if len(parts) != 5 or not variant_id:
                return None
            _variants, _index, _metafields, namespace, key = parts
            return {
                "product": {
                    "variants": [
                        {
                            "id": variant_id,
                            "metafields": {namespace: {key: value}},
                        }
                    ]
                }
            }

        if self._is_product_image_field(field_name):
            return None

        return None

    def _resolve_metafield_upload_value(self, store: str, token: str, field_name: str, file_id: str, file_url: str) -> tuple[bool, str, str]:
        if self._is_product_metafield_field(field_name):
            parts = field_name.split(".", 2)
            if len(parts) != 3:
                return False, "", f"Invalid metafield name: {field_name}"
            _prefix, namespace, key = parts
            owner_type = "PRODUCT"
        elif self._is_variant_metafield_field(field_name):
            parts = field_name.split(".", 4)
            if len(parts) != 5:
                return False, "", f"Invalid variant metafield name: {field_name}"
            _variants, _index, _metafields, namespace, key = parts
            owner_type = "PRODUCTVARIANT"
        else:
            return True, file_url, ""

        definition_type = get_metafield_definition_type(store, token, owner_type, namespace, key)
        if definition_type == "file_reference":
            if not file_id:
                return False, "", "Shopify file upload did not return a file reference id"
            return True, file_id, ""
        if definition_type.startswith("list."):
            return False, "", f"Metafield type '{definition_type}' is not supported by this tab"
        return True, file_url, ""

    def _upload_product_image(self, store: str, token: str, product_id: str, sku: str, img_path: Path) -> tuple[bool, str, str]:
        with open(img_path, "rb") as f:
            img_data = f.read()
        attachment = base64.b64encode(img_data).decode("utf-8")

        payload = {
            "image": {
                "attachment": attachment,
                "alt": f"Product image: {sku}",
            }
        }

        url = f"https://{store}/admin/api/2024-10/products/{product_id}/images.json"
        resp = requests.post(
            url,
            headers={"X-Shopify-Access-Token": token, "Content-Type": "application/json"},
            json=payload,
            timeout=45,
        )
        if not resp.ok:
            error_msg = resp.text[:300] if resp.text else f"HTTP {resp.status_code}"
            return False, "", error_msg

        try:
            body = resp.json()
        except ValueError:
            body = {}
        image = body.get("image", {}) if isinstance(body, dict) else {}
        uploaded_src = str(image.get("src", "")).strip()
        return True, uploaded_src, ""

    def _parse_local_image_sku(self, stem: str) -> tuple[str, str] | None:
        sku = (stem or "").strip()
        if not sku:
            return None
        return sku, ""

    def _image_fields_from_headers(self, headers: list[str]) -> list[str]:
        fields: list[str] = []
        for h in headers:
            key = (h or "").strip()
            if not key:
                continue
            k = key.lower()
            if k in {"id", "variants.0.id", "variants.0.sku", "sku"}:
                continue
            fields.append(key)
        return fields

    def _load_field_options(self) -> None:
        try:
            wb = openpyxl.load_workbook(DATABASE_FILE, read_only=True, data_only=True)
            ws = wb.active
            rows = ws.iter_rows(min_row=1, max_row=1, values_only=True)
            first = next(rows, None)
            headers = [str(h or "").strip() for h in (first or [])]
            wb.close()
        except Exception as exc:
            logger.exception("Failed to load fields from DB")
            self._log(f"Error loading fields: {exc}")
            return

        fields = self._image_fields_from_headers(headers)
        self._field_combo["values"] = fields
        if fields and not self._field_pick.get().strip():
            self._field_pick.set(fields[0])

    def _select_folder(self) -> None:
        current = self._selected_folder.get().strip()
        initial = current if current and Path(current).is_dir() else self._initial_image_folder()
        folder = filedialog.askdirectory(title="Select Image Folder", initialdir=initial)
        if folder:
            self._set_selected_folder(folder)
            self._scan_available_images()

    def _open_selected_folder(self) -> None:
        folder = self._selected_folder.get().strip()
        if not folder:
            folder = self._initial_image_folder()
        if not folder:
            messagebox.showwarning("No Folder", "No image folder available.", parent=self)
            return
        if not Path(folder).is_dir():
            messagebox.showerror("Invalid Folder", f"Folder not found: {folder}", parent=self)
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
        wb = None
        try:
            wb = openpyxl.load_workbook(DATABASE_FILE, data_only=True)
            ws = wb.active
            header_row = next(ws.iter_rows(min_row=1, max_row=1, values_only=True), None)
            headers = [str(h or "").strip() for h in (header_row or [])]
            sku_idx = self._find_col_idx(headers, {"variants.0.sku", "sku"})
            if sku_idx is None:
                self._log("SKU column not found in database headers.")
                self._sku_combo["values"] = []
                return

            skus = []
            for row in ws.iter_rows(min_row=2, values_only=True):
                sku = str(row[sku_idx]).strip() if len(row) > sku_idx and row[sku_idx] else ""
                if sku and sku != DEFAULT_SKU:
                    skus.append(sku)
            self._sku_combo["values"] = skus
        except Exception as e:
            logger.exception("Failed to load SKUs from DB")
            self._log(f"Error loading SKUs: {e}")
        finally:
            if wb is not None:
                try:
                    wb.close()
                except Exception:
                    pass

    def _find_col_idx(self, headers: list[str], accepted: set[str]) -> int | None:
        lowered = [h.lower() for h in headers]
        for name in accepted:
            key = name.lower()
            if key in lowered:
                return lowered.index(key)
        return None

    def _scan_available_images(self) -> None:
        """Scan folder and update tree with available images."""
        folder = self._selected_folder.get().strip()
        if not folder:
            folder = self._initial_image_folder()

        self._tree.delete(*self._tree.get_children())

        if not folder:
            self._log("No folder available.")
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
                    parsed = self._parse_local_image_sku(stem)
                    if not parsed:
                        continue
                    sku, _ = parsed

                    if sku:
                        size_kb = file_path.stat().st_size / 1024
                        images.append((file_path.name, size_kb, sku))
                        self._tree.insert("", "end", values=(file_path.name, f"{size_kb:.1f}", sku))

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
        field_name = self._field_pick.get().strip()

        if not folder:
            messagebox.showwarning("No Folder", "Please select an image folder.", parent=self)
            return

        if not field_name:
            messagebox.showwarning("No Field", "Please select target field first.", parent=self)
            return

        if not self._is_supported_field(field_name):
            messagebox.showerror(
                "Unsupported Field",
                (
                    "This tab currently supports product metafields (metafields.*), "
                    "variant metafields (variants.0.metafields.*), and product image gallery fields "
                    "(images.*.src)."
                ),
                parent=self,
            )
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
        sample_name = "SAMPLESKU.jpg"
        if self._is_variant_metafield_field(field_name):
            field_mode = "Variant metafield"
        elif self._is_product_metafield_field(field_name):
            field_mode = "Product metafield"
        else:
            field_mode = "Product image gallery"
        storage_mode = "Shopify Files" if not self._is_product_image_field(field_name) else "Product gallery"
        msg = (
            f"Upload images from:\n{folder}\n\n"
            f"Field: {field_name}\n"
            f"Field mode: {field_mode}\n"
            f"Storage mode: {storage_mode}\n"
            f"Local filename format: {sample_name}\n"
            f"Scope: {scope_desc}\n\n"
            "Is this correct?"
        )
        if not self._app.confirm("Confirm Image Upload", msg):
            return

        self._running = True
        self._app.start_prog("determinate", use_busy_cursor=False)
        self._log("Upload task started…")

        def task():
            try:
                self._run_upload_task(store, token, folder, sku_set)
            except Exception as exc:
                logger.exception("Upload task crashed")
                self._ui_async(lambda: self._app.stop_prog(clear_busy_cursor=False))
                self._ui_async(lambda: messagebox.showerror("Upload Error", str(exc), parent=self))
            finally:
                self._running = False

        thread = threading.Thread(target=task, daemon=True)
        thread.start()

    def _run_upload_task(self, store: str, token: str, folder: str, sku_set: set[str]) -> None:
        """Execute the upload task."""
        start_time = time.time()
        wb = None
        field_name = self._field_pick.get().strip()

        try:
            # Load database to get SKU->ID mapping
            self._log_step(1, "Loading product database")
            wb = openpyxl.load_workbook(DATABASE_FILE, data_only=True)
            ws = wb.active

            header_row = next(ws.iter_rows(min_row=1, max_row=1, values_only=True), None)
            headers = [str(h or "").strip() for h in (header_row or [])]
            id_idx = self._find_col_idx(headers, {"id"})
            sku_idx = self._find_col_idx(headers, {"variants.0.sku", "sku"})
            variant_id_idx = self._find_col_idx(headers, {"variants.0.id"})
            if id_idx is None or sku_idx is None:
                raise RuntimeError("Database must contain 'id' and 'variants.0.sku' (or 'sku') columns.")

            sku_to_id = {}
            sku_to_variant_id: dict[str, str] = {}
            for row in ws.iter_rows(min_row=2, values_only=True):
                if len(row) <= max(id_idx, sku_idx):
                    continue
                prod_id = str(row[id_idx]).strip() if row[id_idx] else ""
                sku = str(row[sku_idx]).strip() if row[sku_idx] else ""
                if prod_id and sku and sku != DEFAULT_SKU:
                    sku_to_id[sku] = prod_id
                    if variant_id_idx is not None and len(row) > variant_id_idx and row[variant_id_idx]:
                        sku_to_variant_id[sku] = str(row[variant_id_idx]).strip()
            self._log(f"Loaded {len(sku_to_id)} SKU→ID mappings from database")

            # Scan folder for images
            self._log_step(2, "Scanning image folder")
            folder_path = Path(folder)
            images_by_sku: dict[str, list[Path]] = {}

            for file_path in folder_path.glob("*"):
                if file_path.is_file() and file_path.suffix.lower() in IMAGE_EXTENSIONS:
                    stem = file_path.stem
                    parsed = self._parse_local_image_sku(stem)
                    if not parsed:
                        continue
                    sku, _ = parsed

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

            if self._is_variant_metafield_field(field_name):
                missing_variant_ids = [sku for sku in sorted(upload_skus) if sku not in sku_to_variant_id]
                if missing_variant_ids:
                    preview = ", ".join(missing_variant_ids[:10])
                    more = "..." if len(missing_variant_ids) > 10 else ""
                    raise RuntimeError(
                        "Selected variant metafield requires variants.0.id in the database for every SKU. "
                        f"Missing variant ids for: {preview}{more}"
                    )

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
                        # Validate file is readable
                        if not img_path.is_file() or not img_path.stat().st_size:
                            fail_count += 1
                            self._log(f"  [{i + 1}/{len(upload_skus)}] SKU {sku}: {img_path.name} ✗ (not readable or empty)")
                            continue
                        
                        if self._is_product_image_field(field_name):
                            ok_upload, uploaded_value, upload_error = self._upload_product_image(store, token, prod_id, sku, img_path)
                        else:
                            ok_upload, uploaded_file_id, uploaded_file_url, upload_error = upload_file_to_shopify_files(
                                store,
                                token,
                                img_path,
                                alt=f"Product image: {sku}",
                            )
                            if ok_upload:
                                ok_value, uploaded_value, value_error = self._resolve_metafield_upload_value(
                                    store,
                                    token,
                                    field_name,
                                    uploaded_file_id,
                                    uploaded_file_url,
                                )
                                if not ok_value:
                                    fail_count += 1
                                    self._log(f"  [{i + 1}/{len(upload_skus)}] SKU {sku}: {img_path.name} ✗ ({value_error})")
                                    continue
                        if not ok_upload:
                            fail_count += 1
                            self._log(f"  [{i + 1}/{len(upload_skus)}] SKU {sku}: {img_path.name} ✗ ({upload_error})")
                            continue

                        field_payload = self._build_field_update_payload(
                            field_name,
                            uploaded_value,
                            sku_to_variant_id.get(sku, ""),
                        )
                        if not self._is_product_image_field(field_name) and field_payload is None:
                            fail_count += 1
                            self._log(
                                f"  [{i + 1}/{len(upload_skus)}] SKU {sku}: {img_path.name} ✗ "
                                f"(unsupported field mapping: {field_name})"
                            )
                            continue
                        if field_payload is not None:
                            ok_field, _status_field, msg_field = update_product_api(store, token, prod_id, field_payload)
                            if not ok_field:
                                fail_count += 1
                                self._log(f"  [{i + 1}/{len(upload_skus)}] SKU {sku}: {img_path.name} ✗ (field update failed: {msg_field})")
                                continue

                        ok_count += 1
                        self._log(f"  [{i + 1}/{len(upload_skus)}] SKU {sku}: {img_path.name} ✓")

                    except Exception as e:
                        fail_count += 1
                        self._log(f"  [{i + 1}/{len(upload_skus)}] SKU {sku}: {img_path.name} ✗ ({e})")

                # Update progress
                progress = int((i + 1) / len(upload_skus) * 100)
                self._ui_async(lambda p=progress: self._app.set_prog_value(p, 100))

            # Done
            elapsed = time.time() - start_time
            self._log_step(4, f"Upload completed in {elapsed:.1f}s (ok={ok_count}, fail={fail_count}, skip={skip_count})")
            self._ui_async(lambda: self._stats.set(f"Uploaded: {ok_count} images | Failed: {fail_count} | Skipped: {skip_count}"))

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
        finally:
            if wb is not None:
                try:
                    wb.close()
                except Exception:
                    pass

    def _log_step(self, step_no: int, title: str, detail: str = "") -> None:
        if detail:
            self._log(f"[Step {step_no}] {title} — {detail}")
        else:
            self._log(f"[Step {step_no}] {title}")
