"""Work logs viewer tab — view workflow/activity logs in real-time."""

from __future__ import annotations

import csv
import logging
from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox

from ..logger import WORK_TABLE_COLUMNS

logger = logging.getLogger(__name__)


class WorkLogsTab(ttk.Frame):
    """Tab for viewing dedicated workflow logs in real-time."""

    def __init__(self, parent: ttk.Notebook, app):
        super().__init__(parent)
        self._app = app
        self._log_dir = Path("logs")
        self._polling = False
        self._poll_job: str | None = None
        self._last_size: int = 0
        self._all_rows: list[dict[str, str]] = []
        self._build()

    def _build(self) -> None:
        top = ttk.Frame(self)
        top.pack(fill=tk.X, padx=8, pady=8)

        ttk.Label(
            top,
            text="🧾 Work Logs",
            font=("Segoe UI", 10, "bold"),
            foreground="#0f6b45",
        ).pack(side=tk.LEFT)

        ttk.Button(top, text="Refresh", command=self._refresh_logs).pack(side=tk.RIGHT, padx=(4, 0))
        ttk.Button(top, text="Clear Work Logs", command=self._clear_logs).pack(side=tk.RIGHT, padx=(4, 0))
        ttk.Button(top, text="Open Logs Folder", command=self._open_logs_folder).pack(side=tk.RIGHT, padx=(4, 0))

        filters = ttk.Frame(self)
        filters.pack(fill=tk.X, padx=8, pady=(0, 6))
        ttk.Label(filters, text="Product ID:").pack(side=tk.LEFT)
        self._product_filter = tk.StringVar(value="")
        product_entry = ttk.Entry(filters, textvariable=self._product_filter, width=16)
        product_entry.pack(side=tk.LEFT, padx=(6, 8))
        product_entry.bind("<KeyRelease>", lambda _e: self._apply_filters())

        ttk.Label(filters, text="Method:").pack(side=tk.LEFT)
        self._method_filter = tk.StringVar(value="All")
        method_combo = ttk.Combobox(filters, textvariable=self._method_filter, state="readonly", values=["All", "GET", "POST", "PUT", "DELETE"], width=8)
        method_combo.pack(side=tk.LEFT, padx=(6, 8))
        method_combo.bind("<<ComboboxSelected>>", lambda _e: self._apply_filters())

        ttk.Label(filters, text="Status:").pack(side=tk.LEFT)
        self._status_filter = tk.StringVar(value="All")
        status_combo = ttk.Combobox(filters, textvariable=self._status_filter, state="readonly", values=["All", "OK", "FAIL", "EXCEPTION", "GRAPHQL_ERROR"], width=14)
        status_combo.pack(side=tk.LEFT, padx=(6, 8))
        status_combo.bind("<<ComboboxSelected>>", lambda _e: self._apply_filters())

        ttk.Label(filters, text="Outcome:").pack(side=tk.LEFT)
        self._outcome_filter = tk.StringVar(value="")
        outcome_entry = ttk.Entry(filters, textvariable=self._outcome_filter, width=14)
        outcome_entry.pack(side=tk.LEFT, padx=(6, 8))
        outcome_entry.bind("<KeyRelease>", lambda _e: self._apply_filters())

        ttk.Button(filters, text="Clear Filters", command=self._clear_filters).pack(side=tk.LEFT)

        ttk.Label(
            self,
            text="Tracks API sends in table form so you can see what the app called, for which product/field, and the result.",
            foreground="#666",
            font=("Segoe UI", 8),
        ).pack(anchor=tk.W, padx=8, pady=(0, 6))

        table_wrap = ttk.Frame(self)
        table_wrap.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0, 8))
        self._tree = ttk.Treeview(
            table_wrap,
            columns=tuple(WORK_TABLE_COLUMNS),
            show="headings",
            height=18,
        )
        widths = {
            "timestamp": 135,
            "area": 90,
            "operation": 170,
            "method": 70,
            "endpoint": 260,
            "product_id": 110,
            "variant_id": 110,
            "field_name": 130,
            "status_code": 80,
            "outcome": 90,
            "details": 260,
        }
        for column in WORK_TABLE_COLUMNS:
            self._tree.heading(column, text=column)
            self._tree.column(column, width=widths.get(column, 120), anchor=tk.W, stretch=True)

        ysb = ttk.Scrollbar(table_wrap, orient=tk.VERTICAL, command=self._tree.yview)
        xsb = ttk.Scrollbar(table_wrap, orient=tk.HORIZONTAL, command=self._tree.xview)
        self._tree.configure(yscrollcommand=ysb.set, xscrollcommand=xsb.set)
        self._tree.grid(row=0, column=0, sticky="nsew")
        ysb.grid(row=0, column=1, sticky="ns")
        xsb.grid(row=1, column=0, sticky="ew")
        table_wrap.columnconfigure(0, weight=1)
        table_wrap.rowconfigure(0, weight=1)

        self._status = tk.StringVar(value="Ready")
        ttk.Label(self, textvariable=self._status, foreground="#666", font=("Segoe UI", 8)).pack(
            anchor=tk.W, padx=8, pady=(0, 4)
        )

    def _get_log_file(self) -> Path | None:
        if not self._log_dir.exists():
            return None
        log_files = list(self._log_dir.glob("shopify_erp_work_table_*.tsv"))
        if not log_files:
            return None
        log_files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        return log_files[0]

    def _refresh_logs(self) -> None:
        log_file = self._get_log_file()
        if not log_file or not log_file.exists():
            self._tree.delete(*self._tree.get_children())
            self._status.set(f"No work log file found in {self._log_dir}")
            return

        try:
            with open(log_file, "r", encoding="utf-8", errors="replace", newline="") as f:
                reader = csv.DictReader(f, delimiter="\t")
                rows = list(reader)

            self._all_rows = [{column: str(row.get(column, "")) for column in WORK_TABLE_COLUMNS} for row in rows]
            self._apply_filters()

            file_size_kb = log_file.stat().st_size / 1024
            self._status.set(
                f"Viewing: {log_file.name} | Rows: {len(rows)} | Size: {file_size_kb:.1f} KB | Last updated: {datetime.now().strftime('%H:%M:%S')}"
            )
        except Exception as exc:
            logger.error(f"Error refreshing work logs: {exc}")
            self._tree.delete(*self._tree.get_children())
            self._status.set(f"Error: {str(exc)}")

    def _apply_filters(self) -> None:
        product_id = self._product_filter.get().strip().lower()
        method = self._method_filter.get().strip().upper()
        status = self._status_filter.get().strip()
        outcome_text = self._outcome_filter.get().strip().lower()

        filtered_rows: list[dict[str, str]] = []
        for row in self._all_rows:
            if product_id and product_id not in row.get("product_id", "").lower():
                continue
            if method and method != "ALL" and row.get("method", "").upper() != method:
                continue
            if status and status != "All" and row.get("outcome", "") != status:
                continue
            if outcome_text and outcome_text not in row.get("details", "").lower() and outcome_text not in row.get("outcome", "").lower():
                continue
            filtered_rows.append(row)

        self._tree.delete(*self._tree.get_children())
        for row in filtered_rows[-2000:]:
            values = [row.get(column, "") for column in WORK_TABLE_COLUMNS]
            self._tree.insert("", tk.END, values=values)

        children = self._tree.get_children()
        if children:
            self._tree.see(children[-1])

    def _clear_filters(self) -> None:
        self._product_filter.set("")
        self._method_filter.set("All")
        self._status_filter.set("All")
        self._outcome_filter.set("")
        self._apply_filters()

    def _open_logs_folder(self) -> None:
        try:
            if not self._log_dir.exists():
                messagebox.showwarning("Not Found", f"Logs folder not found:\n{self._log_dir.resolve()}", parent=self)
                return

            import subprocess
            import sys
            import os

            if sys.platform == "win32":
                os.startfile(self._log_dir.resolve())
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(self._log_dir.resolve())])
            else:
                subprocess.Popen(["xdg-open", str(self._log_dir.resolve())])
        except Exception as exc:
            logger.error(f"Error opening logs folder: {exc}")
            messagebox.showerror("Error", f"Could not open logs folder:\n{str(exc)}", parent=self)

    def _clear_logs(self) -> None:
        log_file = self._get_log_file()
        if not log_file or not log_file.exists():
            messagebox.showwarning("No Log File", "No work log file found to clear.", parent=self)
            return

        if not self._app.confirm_danger("Clear Work Logs", f"Delete all contents of {log_file.name}?\n\nThis action cannot be undone."):
            return

        try:
            log_file.write_text("", encoding="utf-8")
            messagebox.showinfo("Success", f"Work log file cleared:\n{log_file.name}", parent=self)
            self._refresh_logs()
        except Exception as exc:
            logger.error(f"Error clearing work log file: {exc}")
            messagebox.showerror("Error", f"Could not clear work log file:\n{str(exc)}", parent=self)

    def start_auto_refresh(self) -> None:
        self._polling = True
        self._schedule_refresh()

    def stop_auto_refresh(self) -> None:
        self._polling = False
        if self._poll_job:
            self.after_cancel(self._poll_job)
            self._poll_job = None

    def _schedule_refresh(self) -> None:
        if self._polling:
            self._poll_job = self.after(2000, self._auto_refresh)

    def _auto_refresh(self) -> None:
        try:
            log_file = self._get_log_file()
            if log_file and log_file.exists():
                current_size = log_file.stat().st_size
                if current_size != self._last_size:
                    self._last_size = current_size
                    self._refresh_logs()
        except Exception as exc:
            logger.debug(f"Work log auto-refresh error: {exc}")
        finally:
            self._schedule_refresh()