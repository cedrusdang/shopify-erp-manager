"""
Upload session persistence — allows resuming an interrupted upload.
Session state is stored in upload_session.json.
"""

from __future__ import annotations

import json
from pathlib import Path

SESSION_FILE = Path("upload_session.json")


def save_session(data: dict) -> None:
    SESSION_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")


def load_session() -> dict | None:
    if SESSION_FILE.exists():
        try:
            return json.loads(SESSION_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return None


def clear_session() -> None:
    if SESSION_FILE.exists():
        SESSION_FILE.unlink()
