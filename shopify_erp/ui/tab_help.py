"""
Help / Info tab.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk, scrolledtext

from ..constants import INSTRUCTIONS


class HelpTab(ttk.Frame):
    def __init__(self, parent: ttk.Notebook, app):
        super().__init__(parent)
        self._app = app
        self._build()

    def _build(self) -> None:
        txt = scrolledtext.ScrolledText(self, font=("Segoe UI", 9), wrap=tk.WORD)
        txt.insert(tk.END, INSTRUCTIONS)
        txt.config(state="disabled")
        txt.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)
