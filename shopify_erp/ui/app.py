"""
Main application window.
Owns the connection bar, progress bar, status label, and notebook tabs.
Acts as a shared-state coordinator for all tabs.
"""

from __future__ import annotations

import threading
from datetime import datetime
from pathlib import Path
from tkinter import scrolledtext
import tkinter as tk
from tkinter import ttk, messagebox

from ..api import test_connection
from ..config import load_env
from ..constants import APP_TITLE, APP_VER, CONTACT, DEF_NAME
from ..session import load_session

from .tab_download import DownloadTab
from .tab_upload   import UploadTab
from .tab_backup   import BackupTab
from .tab_settings import SettingsTab
from .tab_help     import HelpTab


class ShopifyERPApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("1020x760")
        self.minsize(860, 640)

        # Shared StringVars consumed by tabs
        self.store = tk.StringVar()
        self.token = tk.StringVar()

        # Pre-fill from .env if available
        env = load_env()
        self.store.set(env.get("SHOPIFY_STORE_DOMAIN", ""))
        self.token.set(env.get("SHOPIFY_ACCESS_TOKEN", ""))

        self._build_ui()

        # Let upload tab know about any saved session
        self._tab_upload.check_resume_session()

    # ──────────────────────────────────────────────────
    #  UI construction
    # ──────────────────────────────────────────────────
    def _build_ui(self) -> None:
        # ── Connection bar ──────────────────────────
        conn = ttk.LabelFrame(self, text=" Shopify Connection ", padding=8)
        conn.pack(fill=tk.X, padx=10, pady=(8, 2))
        conn.columnconfigure(1, weight=1)
        conn.columnconfigure(4, weight=1)

        ttk.Label(conn, text="Store Domain:").grid(
            row=0, column=0, sticky=tk.W, padx=(4, 2)
        )
        ttk.Entry(conn, textvariable=self.store, width=38).grid(
            row=0, column=1, sticky=tk.EW, padx=2
        )
        ttk.Label(
            conn, text="e.g. mystore.myshopify.com",
            foreground="gray", font=("Segoe UI", 8),
        ).grid(row=0, column=2, padx=(2, 12))

        ttk.Label(conn, text="API Token:").grid(
            row=0, column=3, sticky=tk.W, padx=(4, 2)
        )
        ttk.Entry(conn, textvariable=self.token, show="*", width=38).grid(
            row=0, column=4, sticky=tk.EW, padx=2
        )
        ttk.Button(
            conn, text="Test Connection", command=self._test_connection
        ).grid(row=0, column=5, padx=(6, 4))

        # ── Notebook ────────────────────────────────
        nb = ttk.Notebook(self)
        nb.pack(fill=tk.BOTH, expand=True, padx=10, pady=4)

        self._tab_download = DownloadTab(nb, self)
        self._tab_upload   = UploadTab(nb, self)
        self._tab_backup   = BackupTab(nb, self)
        self._tab_settings = SettingsTab(nb, self)
        self._tab_help     = HelpTab(nb, self)

        nb.add(self._tab_download, text="  ⬇  Download  ")
        nb.add(self._tab_upload,   text="  ⬆  Upload  ")
        nb.add(self._tab_backup,   text="  💾  Backup  ")
        nb.add(self._tab_settings, text="  ⚙  Settings  ")
        nb.add(self._tab_help,     text="  ❓  Help  ")

        # ── Bottom status bar ───────────────────────
        bot = ttk.Frame(self)
        bot.pack(fill=tk.X, padx=10, pady=(0, 6))
        self._prog = ttk.Progressbar(bot, length=300, mode="indeterminate")
        self._prog.pack(side=tk.LEFT)
        self._status_var = tk.StringVar(value="Ready")
        ttk.Label(bot, textvariable=self._status_var, anchor=tk.W).pack(
            side=tk.LEFT, padx=8
        )
        ttk.Label(
            bot, text=f"Contact: {CONTACT}",
            foreground="#aaa", font=("Segoe UI", 8),
        ).pack(side=tk.RIGHT)

    # ──────────────────────────────────────────────────
    #  Public helpers used by tabs
    # ──────────────────────────────────────────────────
    def set_status(self, msg: str) -> None:
        self._status_var.set(msg)
        self.update_idletasks()

    def log(self, widget: scrolledtext.ScrolledText, msg: str) -> None:
        widget.config(state="normal")
        widget.insert(tk.END, f"[{datetime.now():%H:%M:%S}] {msg}\n")
        widget.see(tk.END)
        widget.config(state="disabled")

    def start_prog(self, mode: str = "indeterminate") -> None:
        self._prog.config(mode=mode)
        if mode == "indeterminate":
            self._prog.start(10)
        else:
            self._prog.stop()
            self._prog["value"] = 0

    def stop_prog(self) -> None:
        self._prog.stop()
        self._prog.config(mode="determinate", value=0)

    def set_prog_value(self, value: int, maximum: int) -> None:
        self._prog["maximum"] = maximum
        self._prog["value"]   = value

    def confirm(self, title: str, msg: str) -> bool:
        return messagebox.askyesno(title, msg, parent=self)

    def get_conn(self) -> tuple[str | None, str | None]:
        s = self.store.get().strip().rstrip("/")
        t = self.token.get().strip()
        if not s or not t:
            messagebox.showwarning(
                "Missing Credentials",
                "Please enter Store Domain and API Token.",
                parent=self,
            )
            return None, None
        return s, t

    def current_xlsx(self) -> Path:
        return self._tab_download.current_xlsx()

    def notify_backup_created(self) -> None:
        """Called by DownloadTab after a successful backup so BackupTab stays fresh."""
        self._tab_backup.refresh()

    # ──────────────────────────────────────────────────
    #  Connection test
    # ──────────────────────────────────────────────────
    def _test_connection(self) -> None:
        store, token = self.get_conn()
        if not store:
            return

        def task():
            self.start_prog()
            self.set_status("Testing connection…")
            ok, info = test_connection(store, token)
            self.stop_prog()
            if ok:
                self.set_status(f"Connected ✓  {info}")
                messagebox.showinfo("Connected", f"Successfully connected!\n\n{info}", parent=self)
            else:
                self.set_status(f"Failed: {info}")
                messagebox.showerror("Failed", info, parent=self)

        threading.Thread(target=task, daemon=True).start()
