"""
.env loader / saver.
Intentionally avoids python-dotenv so there are no extra dependencies,
but works seamlessly alongside it if installed.
"""

from pathlib import Path

ENV_FILE = Path(".env")

_KEYS = ("SHOPIFY_STORE_DOMAIN", "SHOPIFY_ACCESS_TOKEN")


def load_env() -> dict[str, str]:
    """Parse .env and return {KEY: VALUE} for known keys."""
    result: dict[str, str] = {}
    if not ENV_FILE.exists():
        return result
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        k = k.strip()
        v = v.strip().strip('"').strip("'")
        result[k] = v
    return result


def save_env(store: str, token: str) -> None:
    """Write / update SHOPIFY_* keys in .env (preserves other lines)."""
    existing: dict[str, str] = {}
    other_lines: list[str] = []

    if ENV_FILE.exists():
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped.startswith("#") or "=" not in stripped:
                other_lines.append(line)
                continue
            k, _, v = stripped.partition("=")
            existing[k.strip()] = v.strip()

    existing["SHOPIFY_STORE_DOMAIN"] = store
    existing["SHOPIFY_ACCESS_TOKEN"] = token

    lines = other_lines + [
        f'{k}="{v}"' for k, v in existing.items()
        if not any(ln.startswith(f"{k}=") for ln in other_lines)
    ]
    # Rebuild properly
    out_lines: list[str] = []
    seen: set[str] = set()
    for line in other_lines:
        out_lines.append(line)
    out_lines.append("")
    out_lines.append("# Shopify credentials (set by Shopify ERP Manager)")
    out_lines.append(f'SHOPIFY_STORE_DOMAIN="{store}"')
    out_lines.append(f'SHOPIFY_ACCESS_TOKEN="{token}"')

    ENV_FILE.write_text("\n".join(out_lines) + "\n", encoding="utf-8")
