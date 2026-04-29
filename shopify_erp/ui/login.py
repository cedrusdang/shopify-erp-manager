"""
Login window — shown before the main app.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from ..constants import APP_VER, CONTACT


class LoginWindow(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Shopify ERP — Login")
        self.geometry("400x280")
        self.resizable(False, False)
        self.authenticated = False
        self._build()
        self.mainloop()

    def _build(self) -> None:
        f = ttk.Frame(self, padding=32)
        f.pack(fill=tk.BOTH, expand=True)

        ttk.Label(
            f, text="Shopify ERP Manager",
            font=("Segoe UI", 16, "bold"),
        ).pack(pady=(0, 2))
        ttk.Label(
            f, text=f"v{APP_VER}  ·  {CONTACT}",
            foreground="#888", font=("Segoe UI", 8),
        ).pack()
        ttk.Separator(f).pack(fill=tk.X, pady=16)

        ttk.Label(
            f,
            text="No password required. Press Login to continue.",
            foreground="#666",
            font=("Segoe UI", 9),
            justify=tk.LEFT,
        ).pack(anchor=tk.W, pady=(0, 8))

        ttk.Button(f, text="Login", command=self._login).pack(fill=tk.X, pady=14)
        ttk.Label(
            f, text=f"Contact: {CONTACT}",
            foreground="#aaa", font=("Segoe UI", 8),
        ).pack()

    def _login(self) -> None:
        self.authenticated = True
        self.destroy()
