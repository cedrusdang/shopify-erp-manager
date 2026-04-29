"""
.env loader / saver.
Intentionally avoids python-dotenv so there are no extra dependencies,
but works seamlessly alongside it if installed.
"""

from pathlib import Path

ENV_FILE = Path(".env")

_KEYS = (
    "SHOPIFY_STORE_DOMAIN",
    "SHOPIFY_CLIENT_ID",
    "SHOPIFY_CLIENT_SECRET",
    "SHOPIFY_ACCESS_TOKEN",
)


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


def save_env(
    store: str,
    client_id: str,
    client_secret: str,
    token: str = "",
) -> None:
    """Write Shopify connection credentials to .env."""
    out_lines: list[str] = []
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                out_lines.append(line)
                continue
            key = stripped.partition("=")[0].strip()
            if key in _KEYS:
                continue
            out_lines.append(line)

    if out_lines and out_lines[-1].strip() != "":
        out_lines.append("")
    out_lines.append("# Shopify credentials (set by Shopify ERP Manager)")
    out_lines.append(f'SHOPIFY_STORE_DOMAIN="{store}"')
    out_lines.append(f'SHOPIFY_CLIENT_ID="{client_id}"')
    out_lines.append(f'SHOPIFY_CLIENT_SECRET="{client_secret}"')
    out_lines.append(f'SHOPIFY_ACCESS_TOKEN="{token}"')

    ENV_FILE.write_text("\n".join(out_lines) + "\n", encoding="utf-8")
