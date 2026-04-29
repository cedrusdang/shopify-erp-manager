"""
Main application window.
Owns the connection bar, progress bar, status label, and notebook tabs.
Acts as a shared-state coordinator for all tabs.
"""

from __future__ import annotations

import threading
import logging
from datetime import datetime
from pathlib import Path
from tkinter import scrolledtext
import tkinter as tk
from tkinter import ttk, messagebox

from ..api import fetch_access_token, test_connection
from ..config import load_env
from ..constants import APP_TITLE, APP_VER, CONTACT, DEF_NAME
from ..session import load_session

from .tab_download import DownloadTab
from .tab_upload   import UploadTab
from .tab_backup   import BackupTab
from .tab_settings import SettingsTab
from .tab_help     import HelpTab
from .tab_images_upload import ImagesUploadTab
from .tab_logs     import LogsTab
from .live_database_panel import LiveDatabasePanel

logger = logging.getLogger(__name__)


class ShopifyERPApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        try:
            self.state("zoomed")
        except tk.TclError:
            self.geometry(f"{self.winfo_screenwidth()}x{self.winfo_screenheight()}+0+0")
        self.minsize(860, 640)
        self._configure_styles()

        # Shared StringVars consumed by tabs
        self.store = tk.StringVar()
        self.client_id = tk.StringVar()
        self.client_secret = tk.StringVar()
        self.token = tk.StringVar()

        # Pre-fill from .env if available
        env = load_env()
        self.store.set(env.get("SHOPIFY_STORE_DOMAIN", ""))
        self.client_id.set(env.get("SHOPIFY_CLIENT_ID", ""))
        self.client_secret.set(env.get("SHOPIFY_CLIENT_SECRET", ""))
        self.token.set(env.get("SHOPIFY_ACCESS_TOKEN", ""))

        self._build_ui()
        self._live_db.start_auto_refresh()
        self._live_db_full.start_auto_refresh()
        self._tab_logs.start_auto_refresh()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(300, self._auto_initialize_connection)

        # Let upload tab know about any saved session
        self._tab_upload.check_resume_session()

    # ──────────────────────────────────────────────────
    #  UI construction
    # ──────────────────────────────────────────────────
    def _configure_styles(self) -> None:
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure(
            "Primary.TButton",
            font=("Segoe UI", 9, "bold"),
            foreground="white",
            background="#0f6b45",
            padding=(10, 6),
        )
        style.map(
            "Primary.TButton",
            background=[("active", "#0b5939")],
            foreground=[("active", "white")],
        )

    def _build_ui(self) -> None:
        # ── Connection bar ──────────────────────────
        conn = ttk.LabelFrame(self, text=" Shopify Connection ", padding=8)
        conn.pack(fill=tk.X, padx=10, pady=(8, 2))
        conn.columnconfigure(1, weight=1)
        conn.columnconfigure(3, weight=1)

        ttk.Label(conn, text="(1) Store Domain:").grid(
            row=0, column=0, sticky=tk.W, padx=(4, 2)
        )
        ttk.Entry(conn, textvariable=self.store, width=38).grid(
            row=0, column=1, sticky=tk.EW, padx=2
        )
        ttk.Label(conn, text="(1) Client ID:").grid(
            row=0, column=2, sticky=tk.W, padx=(8, 2)
        )
        ttk.Entry(conn, textvariable=self.client_id, width=34).grid(
            row=0, column=3, sticky=tk.EW, padx=2
        )
        ttk.Button(
            conn,
            text="(2) Get API Token",
            command=self._fetch_token_clicked,
            style="Primary.TButton",
        ).grid(row=0, column=4, padx=(8, 4))

        ttk.Label(
            conn, text="e.g. mystore.myshopify.com",
            foreground="gray", font=("Segoe UI", 8),
        ).grid(row=1, column=1, sticky=tk.W, padx=2)

        ttk.Label(conn, text="(1) Client Secret:").grid(
            row=1, column=2, sticky=tk.W, padx=(8, 2)
        )
        ttk.Entry(conn, textvariable=self.client_secret, show="*", width=34).grid(
            row=1, column=3, sticky=tk.EW, padx=2
        )

        ttk.Label(conn, text="API Token:").grid(
            row=2, column=0, sticky=tk.W, padx=(4, 2), pady=(2, 0)
        )
        self._token_entry = ttk.Entry(conn, textvariable=self.token, show="*", width=38)
        self._token_entry.grid(row=2, column=1, columnspan=3, sticky=tk.EW, padx=2, pady=(2, 0))
        self._token_entry.configure(state="readonly")

        self._show_api_token = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            conn,
            text="Show API Token",
            variable=self._show_api_token,
            command=self._toggle_token_visible,
        ).grid(row=3, column=1, sticky=tk.W, padx=2, pady=(2, 0))

        ttk.Button(
            conn,
            text="Copy Token",
            command=self._copy_token,
        ).grid(row=3, column=3, sticky=tk.E, padx=2, pady=(2, 0))

        ttk.Button(
            conn, text="(2b) Test", command=self._test_connection
        ).grid(row=2, column=4, padx=(8, 4), pady=(2, 0))

        # ── Main split (top workflow + bottom live DB) ──
        split = ttk.Panedwindow(self, orient=tk.VERTICAL)
        split.pack(fill=tk.BOTH, expand=True, padx=10, pady=4)

        top = ttk.Frame(split)
        bottom = ttk.Frame(split)
        split.add(top, weight=3)
        split.add(bottom, weight=2)

        # ── Notebook ────────────────────────────────
        nb = ttk.Notebook(top)
        nb.pack(fill=tk.BOTH, expand=True)
        self._notebook = nb

        self._tab_download = DownloadTab(nb, self)
        self._tab_upload   = UploadTab(nb, self)
        self._tab_backup   = BackupTab(nb, self)
        self._tab_images   = ImagesUploadTab(nb, self)
        self._tab_settings = SettingsTab(nb, self)
        self._tab_help     = HelpTab(nb, self)
        self._tab_logs     = LogsTab(nb, self)

        self._tab_live_full = ttk.Frame(nb)
        self._live_db_full = LiveDatabasePanel(
            self._tab_live_full,
            self,
            title=" Live Database Screen (Full Tab) ",
            max_rows=1200,
        )
        self._live_db_full.pack(fill=tk.BOTH, expand=True)

        nb.add(self._tab_download, text="  ⬇  Download  ")
        nb.add(self._tab_upload,   text="  ⬆  Upload  ")
        nb.add(self._tab_images,   text="  🖼  Images Upload  ")
        nb.add(self._tab_backup,   text="  💾  Backup  ")
        nb.add(self._tab_live_full, text="  🗄  Live DB (Full)  ")
        nb.add(self._tab_logs,     text="  📋  Logs  ")
        nb.add(self._tab_settings, text="  ⚙  Settings  ")
        nb.add(self._tab_help,     text="  ❓  Help  ")
        nb.bind("<<NotebookTabChanged>>", self._on_tab_changed)

        self._live_db = LiveDatabasePanel(bottom, self)
        self._live_db.pack(fill=tk.BOTH, expand=True)
        self._split = split

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

    def confirm_danger(self, title: str, msg: str) -> bool:
        return messagebox.askyesno(title, msg, parent=self)

    def get_conn(self) -> tuple[str | None, str | None]:
        s = self.store.get().strip().rstrip("/")
        t = self.token.get().strip()
        if not s or not t:
            messagebox.showwarning(
                "Missing Credentials",
                "Please enter Store Domain, Client ID, Client Secret, then click 'Get API Token'.",
                parent=self,
            )
            return None, None
        return s, t

    def _set_token(self, value: str) -> None:
        self._token_entry.configure(state="normal")
        self.token.set(value)
        self._token_entry.configure(state="readonly")

    def _toggle_token_visible(self) -> None:
        self._token_entry.configure(state="normal")
        self._token_entry.configure(show="" if self._show_api_token.get() else "*")
        self._token_entry.configure(state="readonly")

    def _copy_token(self) -> None:
        token = self.token.get().strip()
        if not token:
            messagebox.showwarning(
                "No Token",
                "API token is empty. Click 'Get API Token' first.",
                parent=self,
            )
            return
        self.clipboard_clear()
        self.clipboard_append(token)
        self.update()
        messagebox.showinfo("Copied", "API token copied to clipboard.", parent=self)

    def _fetch_token_clicked(self) -> None:
        store = self.store.get().strip().rstrip("/")
        client_id = self.client_id.get().strip()
        client_secret = self.client_secret.get().strip()

        if not store or not client_id or not client_secret:
            logger.warning("Fetch token clicked but missing credentials")
            messagebox.showwarning(
                "Missing Credentials",
                "Please provide Store Domain, Client ID, and Client Secret.",
                parent=self,
            )
            return

        logger.info(f"Fetching token for store: {store}")

        def task():
            try:
                self.start_prog()
                self.set_status("Requesting API token…")
                ok, token_or_error = fetch_access_token(store, client_id, client_secret)
                self.stop_prog()
                if ok:
                    logger.info(f"Successfully fetched token for {store}")
                    self._set_token(token_or_error)
                    self.set_status("API token generated successfully")
                    messagebox.showinfo("Success", "API token generated automatically.", parent=self)
                else:
                    logger.error(f"Failed to fetch token: {token_or_error}")
                    self.set_status("Failed to get API token")
                    messagebox.showerror("Token Error", token_or_error, parent=self)
            except Exception as e:
                logger.exception(f"Error in token fetch task: {e}")
                self.stop_prog()
                self.set_status("Error fetching token")
                messagebox.showerror("Error", f"An error occurred: {str(e)}", parent=self)

        threading.Thread(target=task, daemon=True).start()

    def _auto_initialize_connection(self) -> None:
        """On app startup: auto-fetch API token and auto-test connection."""
        store = self.store.get().strip().rstrip("/")
        client_id = self.client_id.get().strip()
        client_secret = self.client_secret.get().strip()

        if not store or not client_id or not client_secret:
            logger.debug("Auto-init skipped: missing Store/Client credentials")
            self.set_status("Auto-init skipped: missing Store/Client credentials")
            return

        logger.info(f"Auto-initializing connection for store: {store}")

        def task():
            try:
                self.start_prog()
                self.set_status("Auto-init: requesting API token…")
                ok, token_or_error = fetch_access_token(store, client_id, client_secret)
                if not ok:
                    logger.error(f"Auto-init token fetch failed: {token_or_error}")
                    self.stop_prog()
                    self.set_status("Auto-init failed: cannot get API token")
                    return

                self._set_token(token_or_error)
                self.set_status("Auto-init: testing connection…")
                ok_conn, info = test_connection(store, token_or_error)
                self.stop_prog()
                if ok_conn:
                    logger.info(f"Auto-init connection successful: {info}")
                    self.set_status(f"Auto-init connected ✓  {info}")
                else:
                    logger.warning(f"Auto-init connection test failed: {info}")
                    self.set_status(f"Auto-init test failed: {info}")
            except Exception as e:
                logger.exception(f"Error in auto-init task: {e}")
                self.stop_prog()
                self.set_status(f"Auto-init error: {str(e)}")

        threading.Thread(target=task, daemon=True).start()

    def current_xlsx(self) -> Path:
        return self._tab_download.current_xlsx()

    def notify_backup_created(self) -> None:
        """Called by DownloadTab after a successful backup so BackupTab stays fresh."""
        self._tab_backup.refresh()

    def refresh_live_database(self) -> None:
        self._live_db.refresh_data()
        self._live_db_full.refresh_data()

    def _on_tab_changed(self, _event) -> None:
        """Give near-full workspace to dedicated Live DB tab when selected."""
        if self._notebook.select() == str(self._tab_live_full):
            self.after(10, lambda: self._split.sashpos(0, int(self.winfo_height() * 0.92)))
        else:
            self.after(10, lambda: self._split.sashpos(0, int(self.winfo_height() * 0.62)))

    def _on_close(self) -> None:
        self._live_db.stop_auto_refresh()
        self._live_db_full.stop_auto_refresh()
        self._tab_logs.stop_auto_refresh()
        self.destroy()

    # ──────────────────────────────────────────────────
    #  Connection test
    # ──────────────────────────────────────────────────
    def _test_connection(self) -> None:
        store, token = self.get_conn()
        if not store:
            logger.warning("Test connection attempted but no store configured")
            return

        logger.info(f"Testing connection for store: {store}")

        def task():
            try:
                self.start_prog()
                self.set_status("Testing connection…")
                ok, info = test_connection(store, token)
                self.stop_prog()
                if ok:
                    logger.info(f"Connection test successful for {store}: {info}")
                    self.set_status(f"Connected ✓  {info}")
                    messagebox.showinfo("Connected", f"Successfully connected!\n\n{info}", parent=self)
                else:
                    logger.error(f"Connection test failed for {store}: {info}")
                    self.set_status(f"Failed: {info}")
                    messagebox.showerror("Failed", info, parent=self)
            except Exception as e:
                logger.exception(f"Error in connection test task: {e}")
                self.stop_prog()
                self.set_status("Connection test error")
                messagebox.showerror("Error", f"An error occurred: {str(e)}", parent=self)

        threading.Thread(target=task, daemon=True).start()
