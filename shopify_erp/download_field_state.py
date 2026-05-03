"""Persistence for Download tab field list and selection state."""

from __future__ import annotations

import json
from pathlib import Path

STATE_FILE = Path("download_field_state.json")


def load_field_state() -> dict:
    if not STATE_FILE.exists():
        return {}
    try:
        data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if not isinstance(data, dict):
        return {}
    return data


def save_field_state(optional_fields: list[str], selected_fields: list[str]) -> None:
    payload = {
        "optional_fields": list(dict.fromkeys([str(f) for f in optional_fields if str(f).strip()])),
        "selected_fields": list(dict.fromkeys([str(f) for f in selected_fields if str(f).strip()])),
    }
    STATE_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
