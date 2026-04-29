"""Named presets for Download field selections."""

from __future__ import annotations

import json
from pathlib import Path

PRESET_FILE = Path("field_selection_presets.json")


def load_presets() -> list[dict]:
    if not PRESET_FILE.exists():
        return []
    try:
        data = json.loads(PRESET_FILE.read_text(encoding="utf-8"))
    except Exception:
        return []
    if not isinstance(data, list):
        return []

    cleaned: list[dict] = []
    for row in data:
        if not isinstance(row, dict):
            continue
        name = str(row.get("name", "")).strip()
        fields = row.get("fields", [])
        if not name or not isinstance(fields, list):
            continue
        cleaned.append({"name": name, "fields": [str(f) for f in fields if str(f).strip()]})
    return cleaned


def save_presets(presets: list[dict]) -> None:
    PRESET_FILE.write_text(
        json.dumps(presets, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def upsert_preset(name: str, fields: list[str]) -> None:
    key = name.strip()
    if not key:
        raise ValueError("Preset name is required")

    presets = load_presets()
    payload = {"name": key, "fields": list(dict.fromkeys(fields))}
    for i, p in enumerate(presets):
        if p.get("name", "").strip().casefold() == key.casefold():
            presets[i] = payload
            save_presets(presets)
            return

    presets.append(payload)
    save_presets(presets)


def delete_preset(name: str) -> None:
    key = name.strip()
    presets = load_presets()
    new_rows = [p for p in presets if p.get("name", "").strip().casefold() != key.casefold()]
    save_presets(new_rows)
