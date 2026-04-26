"""
Scrollable checkbox field selector widget.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from ..constants import REQUIRED_FIELDS


class FieldSelector(ttk.Frame):
    """Scrollable two-section checkbox list (required + optional)."""

    def __init__(self, parent: tk.Widget, required: list[str], optional: list[str]):
        super().__init__(parent)
        self._req  = list(required)
        self._opt  = list(optional)
        self._vars: dict[str, tk.BooleanVar] = {}
        self._canvas: tk.Canvas | None = None
        self._inner: ttk.Frame | None = None
        self._build()

    # ──────────────────────────────────────────────────
    def _build(self) -> None:
        # Toolbar
        tb = ttk.Frame(self)
        tb.pack(fill=tk.X, pady=(0, 4))
        ttk.Label(tb, text="Product Fields to Export",
                  font=("Segoe UI", 9, "bold")).pack(side=tk.LEFT)
        ttk.Button(tb, text="Select All",
                   command=self._select_all).pack(side=tk.RIGHT, padx=2)
        ttk.Button(tb, text="Deselect All",
                   command=self._deselect_all).pack(side=tk.RIGHT, padx=2)

        # Canvas + scrollbar
        wrap = ttk.Frame(self)
        wrap.pack(fill=tk.BOTH, expand=True)
        self._canvas = tk.Canvas(wrap, borderwidth=0, highlightthickness=0)
        vsb = ttk.Scrollbar(wrap, orient="vertical", command=self._canvas.yview)
        self._canvas.configure(yscrollcommand=vsb.set)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        self._canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self._inner  = ttk.Frame(self._canvas)
        self._win_id = self._canvas.create_window(
            (0, 0), window=self._inner, anchor="nw"
        )
        self._inner.bind(
            "<Configure>",
            lambda _: self._canvas.configure(
                scrollregion=self._canvas.bbox("all")
            ),
        )
        self._canvas.bind(
            "<Configure>",
            lambda e: self._canvas.itemconfig(self._win_id, width=e.width),
        )
        self._canvas.bind(
            "<Enter>", lambda _: self._canvas.bind_all("<MouseWheel>", self._scroll)
        )
        self._canvas.bind(
            "<Leave>", lambda _: self._canvas.unbind_all("<MouseWheel>")
        )
        self._populate()

    def _populate(self) -> None:
        for w in self._inner.winfo_children():  # type: ignore[union-attr]
            w.destroy()
        self._vars.clear()

        ttk.Label(
            self._inner,
            text="  ── Required (always included) ──",
            foreground="#888",
            font=("Segoe UI", 8, "italic"),
        ).pack(anchor=tk.W, pady=(4, 0))
        for f in self._req:
            var = tk.BooleanVar(value=True)
            ttk.Checkbutton(
                self._inner, text=f, variable=var, state="disabled"
            ).pack(anchor=tk.W, padx=16)
            self._vars[f] = var

        ttk.Label(
            self._inner,
            text="  ── Optional ──",
            foreground="#888",
            font=("Segoe UI", 8, "italic"),
        ).pack(anchor=tk.W, pady=(10, 0))
        for f in self._opt:
            var = tk.BooleanVar(value=False)
            ttk.Checkbutton(
                self._inner, text=f, variable=var
            ).pack(anchor=tk.W, padx=16)
            self._vars[f] = var

        self._inner.update_idletasks()  # type: ignore[union-attr]

    def _scroll(self, event: tk.Event) -> None:
        self._canvas.yview_scroll(-1 * (event.delta // 120), "units")  # type: ignore[union-attr]

    def _select_all(self) -> None:
        for f, v in self._vars.items():
            if f not in self._req:
                v.set(True)

    def _deselect_all(self) -> None:
        for f, v in self._vars.items():
            if f not in self._req:
                v.set(False)

    # ── public ─────────────────────────────────────────
    def add_optional_fields(self, fields: list[str]) -> int:
        """Add new fields not already present. Returns count added."""
        added = 0
        for f in fields:
            if f not in self._vars and f not in self._opt:
                self._opt.append(f)
                added += 1
        if added:
            self._populate()
        return added

    def get_selected(self) -> list[str]:
        return [f for f, v in self._vars.items() if v.get()]
