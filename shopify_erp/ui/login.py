"""
Login window — shown before the main app.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk, messagebox

from ..auth import verify
from ..constants import APP_VER, CONTACT


class LoginWindow(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Shopify ERP — Login")
        self.geometry("400x320")
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

        ttk.Label(f, text="Username:").pack(anchor=tk.W)
        self._usr = ttk.Entry(f, width=34)
        self._usr.pack(fill=tk.X, pady=3)
        self._usr.insert(0, "admin")

        ttk.Label(f, text="Password:").pack(anchor=tk.W, pady=(8, 0))
        self._pwd = ttk.Entry(f, show="*", width=34)
        self._pwd.pack(fill=tk.X, pady=3)
        self._pwd.bind("<Return>", lambda _: self._login())

        ttk.Button(f, text="Login", command=self._login).pack(fill=tk.X, pady=14)
        ttk.Label(
            f, text=f"Contact: {CONTACT}",
            foreground="#aaa", font=("Segoe UI", 8),
        ).pack()

    def _login(self) -> None:
        if verify(self._usr.get(), self._pwd.get()):
            self.authenticated = True
            self.destroy()
        else:
            messagebox.showerror("Access Denied", "Invalid username or password.", parent=self)
            self._pwd.delete(0, tk.END)
