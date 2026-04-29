"""Store profile persistence for multiple Shopify stores."""

from __future__ import annotations

import json
from pathlib import Path

PROFILES_FILE = Path("store_profiles.json")


def load_profiles() -> list[dict[str, str]]:
    """Return saved profiles as a list of dicts."""
    if not PROFILES_FILE.exists():
        return []
    try:
        data = json.loads(PROFILES_FILE.read_text(encoding="utf-8"))
        if isinstance(data, list):
            cleaned: list[dict[str, str]] = []
            for item in data:
                if not isinstance(item, dict):
                    continue
                cleaned.append(
                    {
                        "name": str(item.get("name", "")).strip(),
                        "store": str(item.get("store", "")).strip(),
                        "client_id": str(item.get("client_id", "")).strip(),
                        "client_secret": str(item.get("client_secret", "")).strip(),
                    }
                )
            return [p for p in cleaned if p["name"]]
    except Exception:
        pass
    return []


def save_profiles(profiles: list[dict[str, str]]) -> None:
    """Write full profile list to disk."""
    PROFILES_FILE.write_text(
        json.dumps(profiles, indent=2, ensure_ascii=True),
        encoding="utf-8",
    )


def upsert_profile(profile: dict[str, str]) -> None:
    """Create or update a profile by name."""
    profiles = load_profiles()
    name = profile.get("name", "").strip()
    if not name:
        return
    updated = False
    for i, p in enumerate(profiles):
        if p.get("name", "").strip().lower() == name.lower():
            profiles[i] = profile
            updated = True
            break
    if not updated:
        profiles.append(profile)
    save_profiles(sorted(profiles, key=lambda x: x["name"].lower()))


def delete_profile(name: str) -> None:
    """Delete a profile by name."""
    key = name.strip().lower()
    profiles = [p for p in load_profiles() if p.get("name", "").strip().lower() != key]
    save_profiles(profiles)
