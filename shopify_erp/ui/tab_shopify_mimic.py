"""
Shopify Mimic tab — storefront-like preview from local database file.
"""

from __future__ import annotations

import re
from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox

import openpyxl

from ..constants import DATABASE_FILE


class ShopifyMimicTab(ttk.Frame):
    def __init__(self, parent: ttk.Notebook, app):
        super().__init__(parent)
        self._app = app
        self._all_rows: list[dict[str, str]] = []
        self._filtered: list[dict[str, str]] = []
        self._image_refs: list[tk.PhotoImage] = []
        self._page = 1
        self._page_size = 18

        self._query = tk.StringVar(value="")
        self._status = tk.StringVar(value="Ready")
        self._page_text = tk.StringVar(value="Page 1/1")

        self._build()
        self.refresh_data()

    def _build(self) -> None:
        top = ttk.Frame(self)
        top.pack(fill=tk.X, padx=8, pady=8)

        ttk.Label(
            top,
            text="🛍 Shopify Mimic Preview",
            font=("Segoe UI", 10, "bold"),
            foreground="#0f6b45",
        ).pack(side=tk.LEFT)

        ttk.Button(top, text="Refresh", command=self.refresh_data).pack(side=tk.RIGHT, padx=(4, 0))
        ttk.Button(top, text="Search", command=self._apply_filter).pack(side=tk.RIGHT, padx=(4, 0))
        q = ttk.Entry(top, textvariable=self._query, width=30)
        q.pack(side=tk.RIGHT)
        q.bind("<Return>", lambda _e: self._apply_filter())

        nav = ttk.Frame(self)
        nav.pack(fill=tk.X, padx=8, pady=(0, 6))
        ttk.Button(nav, text="◀ Prev", command=self._prev_page).pack(side=tk.LEFT)
        ttk.Button(nav, text="Next ▶", command=self._next_page).pack(side=tk.LEFT, padx=(6, 0))
        ttk.Label(nav, textvariable=self._page_text, foreground="#555").pack(side=tk.LEFT, padx=(10, 0))

        self._canvas = tk.Canvas(self, borderwidth=0, highlightthickness=0)
        ysb = ttk.Scrollbar(self, orient=tk.VERTICAL, command=self._canvas.yview)
        self._canvas.configure(yscrollcommand=ysb.set)
        ysb.pack(side=tk.RIGHT, fill=tk.Y)
        self._canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(8, 0), pady=(0, 6))

        self._inner = ttk.Frame(self._canvas)
        self._inner_win = self._canvas.create_window((0, 0), window=self._inner, anchor="nw")

        self._inner.bind(
            "<Configure>",
            lambda _e: self._canvas.configure(scrollregion=self._canvas.bbox("all")),
        )
        self._canvas.bind(
            "<Configure>",
            lambda e: self._canvas.itemconfig(self._inner_win, width=e.width),
        )

        ttk.Label(self, textvariable=self._status, foreground="#666", font=("Segoe UI", 8)).pack(
            anchor=tk.W, padx=8, pady=(0, 4)
        )

    def _first_non_empty(self, row: tuple, headers: list[str], candidates: list[str]) -> str:
        for c in candidates:
            if c not in headers:
                continue
            idx = headers.index(c)
            if idx < len(row) and row[idx] not in (None, ""):
                return str(row[idx]).strip()
        return ""

    def _resolve_local_image_path(self, src: str) -> tuple[Path | None, str]:
        val = (src or "").strip()
        if not val:
            return None, "N/A"
        if val.lower().startswith("http://") or val.lower().startswith("https://"):
            return None, "Not downloaded yet"

        p = Path(val)
        if not p.is_absolute():
            p = (Path.cwd() / p).resolve()
        if not p.exists():
            return None, "Not downloaded yet"

        return p, "Local file"

    def _load_rows(self) -> list[dict[str, str]]:
        db = Path(DATABASE_FILE)
        if not db.exists():
            return []

        wb = None
        try:
            wb = openpyxl.load_workbook(db, read_only=True, data_only=True)
            ws = wb.active
            rows = list(ws.iter_rows(values_only=True))
            if not rows:
                return []

            headers = [str(h or "").strip() for h in rows[0]]
            image_fields = [h for h in headers if re.match(r"^images\.\d+\.src$", h)]
            if not image_fields and "images.0.src" in headers:
                image_fields = ["images.0.src"]

            out: list[dict[str, str]] = []
            for row in rows[1:]:
                pid = self._first_non_empty(row, headers, ["id"])
                title = self._first_non_empty(row, headers, ["title"])
                handle = self._first_non_empty(row, headers, ["handle"])
                sku = self._first_non_empty(row, headers, ["variants.0.sku", "sku"])
                price = self._first_non_empty(row, headers, ["variants.0.price", "price"])
                status = self._first_non_empty(row, headers, ["status"])
                img_src = self._first_non_empty(row, headers, image_fields)

                if not any([pid, title, handle, sku, price, status, img_src]):
                    continue

                image_path, _image_status = self._resolve_local_image_path(img_src)
                if image_path is None:
                    continue

                out.append(
                    {
                        "id": pid or "N/A",
                        "title": title or "N/A",
                        "handle": handle or "N/A",
                        "sku": sku or "N/A",
                        "price": price or "N/A",
                        "status": status or "N/A",
                        "image_src": img_src,
                    }
                )
            return out
        finally:
            if wb is not None:
                try:
                    wb.close()
                except Exception:
                    pass

    def _apply_filter(self) -> None:
        q = self._query.get().strip().lower()
        if not q:
            self._filtered = list(self._all_rows)
        else:
            self._filtered = [
                r
                for r in self._all_rows
                if q in r["title"].lower()
                or q in r["handle"].lower()
                or q in r["sku"].lower()
                or q in r["id"].lower()
            ]
        self._page = 1
        self._render_page()

    def _max_page(self) -> int:
        if not self._filtered:
            return 1
        return max(1, (len(self._filtered) + self._page_size - 1) // self._page_size)

    def _prev_page(self) -> None:
        self._page = max(1, self._page - 1)
        self._render_page()

    def _next_page(self) -> None:
        self._page = min(self._max_page(), self._page + 1)
        self._render_page()

    def _render_page(self) -> None:
        for w in self._inner.winfo_children():
            w.destroy()
        self._image_refs = []

        if not self._filtered:
            ttk.Label(
                self._inner,
                text="No downloaded products found. Download images first or adjust search.",
                foreground="#666",
            ).pack(anchor=tk.W, padx=8, pady=8)
            self._page_text.set("Page 1/1")
            return

        max_page = self._max_page()
        self._page = min(max(1, self._page), max_page)
        start = (self._page - 1) * self._page_size
        end = min(start + self._page_size, len(self._filtered))
        page_rows = self._filtered[start:end]

        cols = 3
        for i, row in enumerate(page_rows):
            r = i // cols
            c = i % cols

            card = ttk.LabelFrame(self._inner, text=row["title"], padding=8)
            card.grid(row=r, column=c, sticky="nsew", padx=6, pady=6)

            image_path, image_status = self._resolve_local_image_path(row["image_src"])
            image_holder = ttk.Label(card, text="")
            image_holder.pack(anchor=tk.W, pady=(0, 6))

            loaded = False
            if image_path is not None:
                try:
                    img = tk.PhotoImage(file=str(image_path))
                    if img.width() > 220:
                        factor = max(1, img.width() // 220)
                        img = img.subsample(factor, factor)
                    self._image_refs.append(img)
                    image_holder.configure(image=img)
                    loaded = True
                except Exception:
                    loaded = False

            if not loaded:
                image_holder.configure(
                    text=f"Image: {image_status}",
                    foreground="#666",
                    font=("Segoe UI", 8, "italic"),
                )

            ttk.Label(card, text=f"Handle: {row['handle']}").pack(anchor=tk.W)
            ttk.Label(card, text=f"SKU: {row['sku']}").pack(anchor=tk.W)
            ttk.Label(card, text=f"Price: {row['price']}").pack(anchor=tk.W)
            ttk.Label(card, text=f"Status: {row['status']}").pack(anchor=tk.W)
            ttk.Label(card, text=f"ID: {row['id']}", foreground="#666").pack(anchor=tk.W)

        for c in range(cols):
            self._inner.grid_columnconfigure(c, weight=1)

        self._page_text.set(f"Page {self._page}/{max_page}")

    def refresh_data(self) -> None:
        try:
            self._all_rows = self._load_rows()
            self._apply_filter()
            self._status.set(
                f"Loaded {len(self._all_rows)} downloaded products from {DATABASE_FILE}."
            )
        except Exception as exc:
            self._status.set(f"Error: {exc}")
            messagebox.showerror("Mimic Preview Error", str(exc), parent=self)
