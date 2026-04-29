"""
Logs viewer tab — view application logs in real-time.
"""

from __future__ import annotations

import threading
import logging
from datetime import datetime
from pathlib import Path
from tkinter import scrolledtext
import tkinter as tk
from tkinter import ttk, messagebox

logger = logging.getLogger(__name__)


class LogsTab(ttk.Frame):
    """Tab for viewing application logs in real-time."""

    def __init__(self, parent: ttk.Notebook, app):
        super().__init__(parent)
        self._app = app
        self._log_dir = Path("logs")
        self._polling = False
        self._poll_job: str | None = None
        self._last_size: int = 0
        self._build()

    def _build(self) -> None:
        # Top controls
        top = ttk.Frame(self)
        top.pack(fill=tk.X, padx=8, pady=8)

        ttk.Label(
            top,
            text="📋 Application Logs",
            font=("Segoe UI", 10, "bold"),
            foreground="#0f6b45",
        ).pack(side=tk.LEFT)

        ttk.Button(top, text="Refresh", command=self._refresh_logs).pack(side=tk.RIGHT, padx=(4, 0))
        ttk.Button(top, text="Clear Logs", command=self._clear_logs).pack(side=tk.RIGHT, padx=(4, 0))
        ttk.Button(top, text="Open Logs Folder", command=self._open_logs_folder).pack(side=tk.RIGHT, padx=(4, 0))

        # Log type selector
        controls = ttk.Frame(self)
        controls.pack(fill=tk.X, padx=8, pady=(0, 6))
        ttk.Label(controls, text="Log Type:").pack(side=tk.LEFT)
        self._log_type = tk.StringVar(value="main")
        log_combo = ttk.Combobox(
            controls,
            textvariable=self._log_type,
            state="readonly",
            values=["Main Log", "Error Log"],
            width=20,
        )
        log_combo.pack(side=tk.LEFT, padx=(6, 8))
        log_combo.bind("<<ComboboxSelected>>", lambda _: self._refresh_logs())

        ttk.Label(controls, text="Auto-refresh every 2 seconds", foreground="#666", font=("Segoe UI", 8)).pack(
            side=tk.LEFT, padx=(8, 0)
        )

        # Log display
        self._log_text = scrolledtext.ScrolledText(
            self, state="disabled", font=("Consolas", 9), wrap=tk.WORD
        )
        self._log_text.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0, 8))

        # Configure tags for highlighting
        self._log_text.tag_config("INFO", foreground="#0b5939")
        self._log_text.tag_config("DEBUG", foreground="#666")
        self._log_text.tag_config("WARNING", foreground="#b8860b", font=("Consolas", 9, "bold"))
        self._log_text.tag_config("ERROR", foreground="#dc143c", font=("Consolas", 9, "bold"))
        self._log_text.tag_config("CRITICAL", foreground="#8b0000", font=("Consolas", 9, "bold"))

        # Status bar
        self._status = tk.StringVar(value="Ready")
        ttk.Label(self, textvariable=self._status, foreground="#666", font=("Segoe UI", 8)).pack(
            anchor=tk.W, padx=8, pady=(0, 4)
        )

    def _get_log_file(self) -> Path | None:
        """Get the current log file based on selection."""
        if not self._log_dir.exists():
            return None

        log_files = list(self._log_dir.glob("shopify_erp_*.log"))
        if not log_files:
            return None

        # Sort by modification time, get the most recent
        log_files.sort(key=lambda p: p.stat().st_mtime, reverse=True)

        log_type = self._log_type.get()
        if "Error" in log_type:
            # Find error log
            for f in log_files:
                if "errors" in f.name:
                    return f
        else:
            # Find main log
            for f in log_files:
                if "errors" not in f.name:
                    return f

        return log_files[0] if log_files else None

    def _refresh_logs(self) -> None:
        """Refresh the log display."""
        log_file = self._get_log_file()
        if not log_file or not log_file.exists():
            self._log_text.config(state="normal")
            self._log_text.delete(1.0, tk.END)
            self._log_text.insert(tk.END, "No log file found.\n\nLogs will appear here when the application runs.")
            self._log_text.config(state="disabled")
            self._status.set(f"No log file found in {self._log_dir}")
            return

        try:
            with open(log_file, "r", encoding="utf-8") as f:
                content = f.read()

            self._log_text.config(state="normal")
            self._log_text.delete(1.0, tk.END)

            # Insert content with syntax highlighting
            for line in content.split("\n"):
                self._log_text.insert(tk.END, line + "\n")
                # Apply color tags based on log level
                if "| ERROR" in line or "| CRITICAL" in line:
                    line_end = f"{self._log_text.index('end-1c')} lineend"
                    line_start = f"{self._log_text.index('end-1c')} linestart"
                    if "CRITICAL" in line:
                        self._log_text.tag_add("CRITICAL", line_start, line_end)
                    else:
                        self._log_text.tag_add("ERROR", line_start, line_end)
                elif "| WARNING" in line:
                    line_end = f"{self._log_text.index('end-1c')} lineend"
                    line_start = f"{self._log_text.index('end-1c')} linestart"
                    self._log_text.tag_add("WARNING", line_start, line_end)
                elif "| INFO" in line:
                    line_end = f"{self._log_text.index('end-1c')} lineend"
                    line_start = f"{self._log_text.index('end-1c')} linestart"
                    self._log_text.tag_add("INFO", line_start, line_end)
                elif "| DEBUG" in line:
                    line_end = f"{self._log_text.index('end-1c')} lineend"
                    line_start = f"{self._log_text.index('end-1c')} linestart"
                    self._log_text.tag_add("DEBUG", line_start, line_end)

            # Scroll to the end
            self._log_text.see(tk.END)
            self._log_text.config(state="disabled")

            file_size = log_file.stat().st_size
            file_size_kb = file_size / 1024
            self._status.set(f"Viewing: {log_file.name} | Size: {file_size_kb:.1f} KB | Last updated: {datetime.now().strftime('%H:%M:%S')}")

        except Exception as exc:
            logger.error(f"Error refreshing logs: {exc}")
            self._log_text.config(state="normal")
            self._log_text.delete(1.0, tk.END)
            self._log_text.insert(tk.END, f"Error reading log file:\n{str(exc)}")
            self._log_text.config(state="disabled")
            self._status.set(f"Error: {str(exc)}")

    def _open_logs_folder(self) -> None:
        """Open the logs folder in file explorer."""
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

            logger.info(f"Opened logs folder: {self._log_dir.resolve()}")
        except Exception as exc:
            logger.error(f"Error opening logs folder: {exc}")
            messagebox.showerror("Error", f"Could not open logs folder:\n{str(exc)}", parent=self)

    def _clear_logs(self) -> None:
        """Clear the current log file."""
        log_file = self._get_log_file()
        if not log_file or not log_file.exists():
            messagebox.showwarning("No Log File", "No log file found to clear.", parent=self)
            return

        if not self._app.confirm("Clear Logs", f"Delete all contents of {log_file.name}?\n\nThis action cannot be undone."):
            return

        try:
            log_file.write_text("")
            logger.info(f"Log file cleared: {log_file.name}")
            messagebox.showinfo("Success", f"Log file cleared:\n{log_file.name}", parent=self)
            self._refresh_logs()
        except Exception as exc:
            logger.error(f"Error clearing log file: {exc}")
            messagebox.showerror("Error", f"Could not clear log file:\n{str(exc)}", parent=self)

    def start_auto_refresh(self) -> None:
        """Start auto-refreshing logs."""
        self._polling = True
        self._schedule_refresh()

    def stop_auto_refresh(self) -> None:
        """Stop auto-refreshing logs."""
        self._polling = False
        if self._poll_job:
            self.after_cancel(self._poll_job)
            self._poll_job = None

    def _schedule_refresh(self) -> None:
        if self._polling:
            self._poll_job = self.after(2000, self._auto_refresh)

    def _auto_refresh(self) -> None:
        """Auto-refresh logs if there are changes."""
        try:
            log_file = self._get_log_file()
            if log_file and log_file.exists():
                current_size = log_file.stat().st_size
                if current_size != self._last_size:
                    self._last_size = current_size
                    self._refresh_logs()
        except Exception as exc:
            logger.debug(f"Auto-refresh error: {exc}")
        finally:
            self._schedule_refresh()
