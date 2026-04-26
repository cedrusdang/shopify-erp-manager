"""
Settings tab — load / save Shopify credentials to/from .env.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk, messagebox

from ..config import load_env, save_env


class SettingsTab(ttk.Frame):
    def __init__(self, parent: ttk.Notebook, app):
        super().__init__(parent)
        self._app = app
        self._build()

    # ──────────────────────────────────────────────────
    def _build(self) -> None:
        pad = ttk.Frame(self, padding=24)
        pad.pack(fill=tk.BOTH, expand=True)

        # ── .env section ────────────────────────────
        env_frame = ttk.LabelFrame(pad, text=" Credentials (.env) ", padding=14)
        env_frame.pack(fill=tk.X, pady=(0, 16))
        env_frame.columnconfigure(1, weight=1)

        ttk.Label(env_frame, text="Store Domain:").grid(row=0, column=0, sticky=tk.W, pady=4, padx=(0, 8))
        self._env_store = ttk.Entry(env_frame, width=50)
        self._env_store.grid(row=0, column=1, sticky=tk.EW)
        ttk.Label(
            env_frame, text="e.g. mystore.myshopify.com",
            foreground="gray", font=("Segoe UI", 8),
        ).grid(row=0, column=2, padx=(6, 0))

        ttk.Label(env_frame, text="API Token:").grid(row=1, column=0, sticky=tk.W, pady=4, padx=(0, 8))
        self._env_token = ttk.Entry(env_frame, width=50, show="*")
        self._env_token.grid(row=1, column=1, sticky=tk.EW)

        self._show_token = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            env_frame, text="Show token",
            variable=self._show_token,
            command=self._toggle_show,
        ).grid(row=1, column=2, padx=(6, 0))

        btns = ttk.Frame(env_frame)
        btns.grid(row=2, column=0, columnspan=3, pady=(12, 0), sticky=tk.W)
        ttk.Button(btns, text="📂  Load from .env",   command=self._load).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(btns, text="💾  Save to .env",      command=self._save).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(btns, text="➡  Apply to Connection bar", command=self._apply).pack(side=tk.LEFT)

        # ── Info ────────────────────────────────────
        info = ttk.LabelFrame(pad, text=" Info ", padding=14)
        info.pack(fill=tk.X)
        ttk.Label(
            info,
            text=(
                "• .env is stored in the working directory and excluded from git.\n"
                "• 'Apply to Connection bar' copies these values to the top connection bar\n"
                "  without saving, so they only last for the current session.\n"
                "• 'Save to .env' persists them for next launch."
            ),
            justify=tk.LEFT,
            foreground="#444",
            font=("Segoe UI", 9),
        ).pack(anchor=tk.W)

        # Auto-populate from .env on open
        self._load(silent=True)

    # ──────────────────────────────────────────────────
    def _toggle_show(self) -> None:
        self._env_token.config(show="" if self._show_token.get() else "*")

    def _load(self, *, silent: bool = False) -> None:
        env = load_env()
        s = env.get("SHOPIFY_STORE_DOMAIN", "")
        t = env.get("SHOPIFY_ACCESS_TOKEN", "")
        self._env_store.delete(0, tk.END)
        self._env_store.insert(0, s)
        self._env_token.delete(0, tk.END)
        self._env_token.insert(0, t)
        if not silent:
            messagebox.showinfo(
                "Loaded", "Credentials loaded from .env.", parent=self
            )

    def _save(self) -> None:
        s = self._env_store.get().strip()
        t = self._env_token.get().strip()
        if not s or not t:
            messagebox.showwarning(
                "Incomplete", "Please enter both Store Domain and API Token.", parent=self
            )
            return
        if not self._app.confirm(
            "Save to .env",
            "Save credentials to .env?\n\n"
            "The file will be created / updated in the current working directory.",
        ):
            return
        try:
            save_env(s, t)
            messagebox.showinfo("Saved", "Credentials saved to .env.", parent=self)
        except Exception as exc:
            messagebox.showerror("Error", str(exc), parent=self)

    def _apply(self) -> None:
        s = self._env_store.get().strip()
        t = self._env_token.get().strip()
        if not s or not t:
            messagebox.showwarning(
                "Incomplete", "Please enter both Store Domain and API Token.", parent=self
            )
            return
        self._app.store.set(s)
        self._app.token.set(t)
        messagebox.showinfo(
            "Applied",
            "Credentials applied to the connection bar.\n"
            "(Not saved to disk — use 'Save to .env' to persist.)",
            parent=self,
        )
