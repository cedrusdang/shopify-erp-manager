"""
Backup tab — list, create, and rollback timestamped Excel backups.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk, messagebox

from ..backup import create_backup, list_backups, rollback


class BackupTab(ttk.Frame):
    def __init__(self, parent: ttk.Notebook, app):
        super().__init__(parent)
        self._app = app
        self._build()

    # ──────────────────────────────────────────────────
    def _build(self) -> None:
        ttk.Label(
            self, text="Available Backups",
            font=("Segoe UI", 10, "bold"),
        ).pack(anchor=tk.W, padx=10, pady=6)

        wrap = ttk.Frame(self)
        wrap.pack(fill=tk.BOTH, expand=True, padx=10, pady=4)
        vsb = ttk.Scrollbar(wrap)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        self._list = tk.Listbox(
            wrap, yscrollcommand=vsb.set,
            font=("Consolas", 9), selectmode=tk.SINGLE,
        )
        vsb.config(command=self._list.yview)
        self._list.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        btns = ttk.Frame(self)
        btns.pack(fill=tk.X, padx=10, pady=8)
        ttk.Button(btns, text="🔄  Refresh",     command=self.refresh).pack(side=tk.LEFT, padx=4)
        ttk.Button(btns, text="💾  Backup Now",  command=self._manual_backup).pack(side=tk.LEFT, padx=4)
        ttk.Button(btns, text="⏪  Rollback",    command=self._rollback).pack(side=tk.LEFT, padx=4)

        self.refresh()

    # ──────────────────────────────────────────────────
    def refresh(self) -> None:
        self._list.delete(0, tk.END)
        for b in list_backups():
            kb = b.stat().st_size // 1024
            self._list.insert(tk.END, f"{b.name}  ({kb} KB)")
        self.update_idletasks()

    def _manual_backup(self) -> None:
        target = self._app.current_xlsx()
        if not target.exists():
            messagebox.showwarning("Not Found", f"File not found:\n{target.resolve()}", parent=self)
            return
        if self._app.confirm("Create Backup", f"Create a timestamped backup of:\n{target.name}?"):
            bk = create_backup(target)
            self.refresh()
            messagebox.showinfo("Backup Created", f"Saved as:\n{bk.name}", parent=self)

    def _rollback(self) -> None:
        sel = self._list.curselection()
        if not sel:
            messagebox.showwarning("No Selection", "Select a backup to roll back to.", parent=self)
            return
        backups = list_backups()
        bk      = backups[sel[0]]
        target  = self._app.current_xlsx()
        if self._app.confirm_danger(
            "Confirm Rollback",
            f"Restore backup:\n{bk.name}\n\n"
            f"→  {target.resolve()}\n\n"
            f"The current file will be overwritten. Continue?",
        ):
            try:
                rollback(bk, target)
                messagebox.showinfo("Rollback Complete", f"Restored:\n{bk.name}", parent=self)
                self._app.set_status(f"Rolled back to {bk.name}")
            except Exception as exc:
                messagebox.showerror("Error", str(exc), parent=self)
