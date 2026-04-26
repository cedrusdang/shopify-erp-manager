"""
Backup helpers: create, list, and rollback timestamped Excel backups.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import os
from datetime import datetime
from pathlib import Path

BACKUP_DIR = Path("backups")


def _ensure_backup_dir() -> None:
    BACKUP_DIR.mkdir(exist_ok=True)


def create_backup(src: Path) -> Path:
    """Copy *src* to backups/shopify_database_YYYYMMDD_HHMMSS.xlsx."""
    _ensure_backup_dir()
    ts   = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = BACKUP_DIR / f"shopify_database_{ts}.xlsx"
    shutil.copy2(src, dest)
    return dest


def list_backups() -> list[Path]:
    """Return timestamped backup files, newest first."""
    _ensure_backup_dir()
    return sorted(BACKUP_DIR.glob("shopify_database_*.xlsx"), reverse=True)


def rollback(backup: Path, target: Path) -> None:
    """Overwrite *target* with *backup*."""
    shutil.copy2(backup, target)


def open_file(path: Path) -> bool:
    """Open *path* with the default system application."""
    if not path.exists():
        return False
    try:
        if sys.platform == "win32":
            os.startfile(str(path.resolve()))
        elif sys.platform == "darwin":
            subprocess.run(["open", str(path)])
        else:
            subprocess.run(["xdg-open", str(path)])
        return True
    except Exception:
        return False
