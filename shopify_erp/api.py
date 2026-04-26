"""
Shopify REST API helpers.
All network calls are isolated here so the UI stays thin.
"""

from __future__ import annotations

import re
import time
from typing import Callable

import requests

from .constants import API_VER


# ──────────────────────────────────────────────────────────
#  Shared headers
# ──────────────────────────────────────────────────────────
def _headers(token: str) -> dict[str, str]:
    return {
        "X-Shopify-Access-Token": token,
        "Content-Type": "application/json",
    }


# ──────────────────────────────────────────────────────────
#  Utility
# ──────────────────────────────────────────────────────────
def get_by_path(obj: object, path: str) -> object:
    """Extract a nested value using dot-notation (e.g. 'variants.0.sku')."""
    try:
        for k in path.split("."):
            obj = obj[int(k)] if k.isdigit() else obj[k]  # type: ignore[index]
        return "" if obj is None else obj
    except Exception:
        return ""


# ──────────────────────────────────────────────────────────
#  Read operations
# ──────────────────────────────────────────────────────────
def test_connection(store: str, token: str) -> tuple[bool, str]:
    """Return (ok, shop_name_or_error)."""
    try:
        r = requests.get(
            f"https://{store}/admin/api/{API_VER}/shop.json",
            headers=_headers(token),
            timeout=15,
        )
        if r.ok:
            return True, r.json().get("shop", {}).get("name", store)
        return False, f"HTTP {r.status_code}: {r.text[:200]}"
    except requests.RequestException as exc:
        return False, str(exc)


def fetch_all_products(
    store: str,
    token: str,
    on_progress: Callable[[str], None] | None = None,
) -> list[dict]:
    """Fetch every product via paginated REST (250/page). Returns list of dicts."""
    url: str | None = (
        f"https://{store}/admin/api/{API_VER}/products.json?limit=250"
    )
    products: list[dict] = []
    page = 1
    while url:
        if on_progress:
            on_progress(f"Fetching page {page}…  ({len(products)} loaded so far)")
        resp = requests.get(url, headers=_headers(token), timeout=30)
        resp.raise_for_status()
        products.extend(resp.json().get("products", []))
        link = resp.headers.get("Link", "")
        m = re.search(r'<([^>]+)>;\s*rel="next"', link)
        url = m.group(1) if m else None
        page += 1
    return products


def fetch_metafield_definitions(store: str, token: str) -> list[str]:
    """Return flat dot-notation paths for all metafield definitions."""
    gql_url = f"https://{store}/admin/api/{API_VER}/graphql.json"
    results: list[str] = []
    for owner, prefix in [
        ("PRODUCT", "metafields"),
        ("PRODUCTVARIANT", "variants.0.metafields"),
    ]:
        query = (
            "{ metafieldDefinitions(first: 250, ownerType: %s) "
            "{ edges { node { namespace key } } } }" % owner
        )
        try:
            resp = requests.post(
                gql_url,
                headers=_headers(token),
                json={"query": query},
                timeout=30,
            )
            if resp.ok:
                edges = (
                    resp.json()
                    .get("data", {})
                    .get("metafieldDefinitions", {})
                    .get("edges", [])
                )
                for e in edges:
                    n = e["node"]
                    results.append(f"{prefix}.{n['namespace']}.{n['key']}")
        except Exception:
            pass
    return results


# ──────────────────────────────────────────────────────────
#  Write operations
# ──────────────────────────────────────────────────────────
def update_product_api(
    store: str,
    token: str,
    product_id: str,
    payload: dict,
    max_retries: int = 5,
) -> tuple[bool, int, str]:
    """PUT a single product. Returns (ok, status_code, error_message)."""
    url = f"https://{store}/admin/api/{API_VER}/products/{product_id}.json"
    wait = 1
    for attempt in range(max_retries):
        try:
            resp = requests.put(
                url, headers=_headers(token), json=payload, timeout=30
            )
            if 200 <= resp.status_code < 300:
                return True, resp.status_code, ""
            if resp.status_code in (429, 500, 502, 503, 504):
                time.sleep(wait)
                wait = min(wait * 2, 32)
            else:
                try:
                    err = resp.json().get("errors", resp.text[:300])
                except Exception:
                    err = resp.text[:300]
                return False, resp.status_code, str(err)
        except requests.RequestException as exc:
            time.sleep(wait)
            wait = min(wait * 2, 32)
    return False, 0, f"Max retries exceeded ({max_retries})"
