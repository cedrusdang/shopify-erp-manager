"""Shopify API helpers (REST-first for product flows)."""

from __future__ import annotations

import re
import time
import logging
from typing import Callable
from urllib.parse import quote, unquote

import requests

from .constants import API_VER

logger = logging.getLogger(__name__)

# Fast-path cache for metafield uploads:
# verify once (first owner/first SKU), then reuse known type/strategy for next rows.
_METAFIELD_VERIFY_CACHE: dict[tuple[str, str, str], dict[str, str]] = {}


# ──────────────────────────────────────────────────────────
#  Shared headers
# ──────────────────────────────────────────────────────────
def _headers(token: str) -> dict[str, str]:
    return {
        "X-Shopify-Access-Token": token,
        "Content-Type": "application/json",
    }


def _rest_base_url(store: str) -> str:
    return f"https://{store}/admin/api/{API_VER}"


def _parse_next_page_info(link_header: str) -> str | None:
    if not link_header:
        return None
    m = re.search(r"<[^>]*[?&]page_info=([^&>]+)[^>]*>;\s*rel=\"next\"", link_header)
    if not m:
        return None
    return unquote(m.group(1))


def _rest_get_products_page(
    store: str,
    token: str,
    page_info: str | None = None,
    limit: int = 250,
) -> tuple[list[dict], str | None]:
    url = f"{_rest_base_url(store)}/products.json"
    if page_info:
        params = {"limit": limit, "page_info": page_info}
    else:
        params = {"limit": limit, "published_status": "any"}
    resp = requests.get(url, headers=_headers(token), params=params, timeout=30)
    if not resp.ok:
        raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:300]}")
    body = resp.json()
    products = body.get("products", []) if isinstance(body, dict) else []
    next_page_info = _parse_next_page_info(resp.headers.get("Link", ""))
    return products, next_page_info


def _rest_product_to_internal(p: dict) -> dict:
    variants: list[dict] = []
    for v in p.get("variants", []) or []:
        variants.append(
            {
                "id": str(v.get("id", "")),
                "sku": v.get("sku") or "",
                "title": v.get("title") or "",
                "price": v.get("price") or "",
                "compare_at_price": v.get("compare_at_price") or "",
                "inventory_quantity": v.get("inventory_quantity") or "",
                "barcode": v.get("barcode") or "",
                "weight": v.get("weight") or "",
                "weight_unit": v.get("weight_unit") or "",
                "option1": v.get("option1") or "",
                "option2": v.get("option2") or "",
                "option3": v.get("option3") or "",
                "taxable": v.get("taxable"),
                "requires_shipping": v.get("requires_shipping"),
            }
        )

    images: list[dict] = []
    for img in p.get("images", []) or []:
        src = img.get("src") or ""
        if src:
            images.append(
                {
                    "id": str(img.get("id", "")),
                    "src": src,
                    "alt": img.get("alt") or "",
                }
            )

    admin_gid = p.get("admin_graphql_api_id") or _to_gid("Product", p.get("id", ""))
    return {
        "id": str(p.get("id", "")),
        "admin_graphql_api_id": admin_gid,
        "title": p.get("title") or "",
        "body_html": p.get("body_html") or "",
        "vendor": p.get("vendor") or "",
        "product_type": p.get("product_type") or "",
        "tags": p.get("tags") or "",
        "status": str(p.get("status") or "").lower(),
        "handle": p.get("handle") or "",
        "created_at": p.get("created_at") or "",
        "updated_at": p.get("updated_at") or "",
        "published_at": p.get("published_at") or "",
        "template_suffix": p.get("template_suffix") or "",
        "variants": variants,
        "images": images,
    }


def _to_gid(kind: str, raw_id: str | int) -> str:
    s = str(raw_id).strip()
    if s.startswith("gid://"):
        return s
    return f"gid://shopify/{kind}/{s}"


def _gid_tail(gid_or_id: str) -> str:
    s = str(gid_or_id or "")
    return s.rsplit("/", 1)[-1]


def fetch_access_token(
    store: str,
    client_id: str,
    client_secret: str,
) -> tuple[bool, str]:
    """Exchange client credentials for an Admin API access token."""
    url = f"https://{store}/admin/oauth/access_token"
    data = {
        "grant_type": "client_credentials",
        "client_id": client_id,
        "client_secret": client_secret,
    }
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
    }
    try:
        logger.debug(f"Fetching access token from {store}")
        resp = requests.post(url, headers=headers, data=data, timeout=20)
        if not resp.ok:
            err_msg = f"HTTP {resp.status_code}: {resp.text[:300]}"
            logger.error(f"Failed to fetch token: {err_msg}")
            return False, err_msg
        body = resp.json()
        token = body.get("access_token", "").strip()
        if not token:
            logger.error("No access_token found in token response")
            return False, "No access_token found in response."
        logger.info(f"Successfully fetched access token for {store}")
        return True, token
    except requests.RequestException as exc:
        logger.error(f"Token request exception: {exc}", exc_info=True)
        return False, str(exc)
    except ValueError as exc:
        logger.error(f"Token response JSON parse error: {exc}", exc_info=True)
        return False, "Token response is not valid JSON."


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
        url = f"{_rest_base_url(store)}/shop.json"
        resp = requests.get(url, headers=_headers(token), timeout=15)
        if not resp.ok:
            return False, f"HTTP {resp.status_code}: {resp.text[:300]}"
        body = resp.json()
        return True, body.get("shop", {}).get("name", store)
    except requests.RequestException as exc:
        return False, str(exc)
    except ValueError:
        return False, "Shop response is not valid JSON."


def fetch_first_variant_id(store: str, token: str, product_id: str) -> str | None:
    """Return first variant id for a product, or None if unavailable."""
    pid = _gid_tail(str(product_id or "").strip())
    if not pid:
        return None
    try:
        url = f"{_rest_base_url(store)}/products/{quote(pid)}.json"
        resp = requests.get(
            url,
            headers=_headers(token),
            params={"fields": "id,variants"},
            timeout=30,
        )
        if not resp.ok:
            return None
        body = resp.json()
        prod = body.get("product", {}) if isinstance(body, dict) else {}
        variants = prod.get("variants", []) if isinstance(prod, dict) else []
        if not isinstance(variants, list):
            return None
        for v in variants:
            if not isinstance(v, dict):
                continue
            vid = str(v.get("id", "")).strip()
            if vid:
                return vid
        return None
    except Exception:
        return None


def fetch_all_products(
    store: str,
    token: str,
    on_progress: Callable[[str], None] | None = None,
) -> list[dict]:
    """Fetch every product via REST cursor pagination."""
    page_info: str | None = None
    seen_page_info: set[str] = set()
    products: list[dict] = []
    page = 1
    max_pages = 2000
    while True:
        if page > max_pages:
            raise RuntimeError(f"Pagination aborted: exceeded {max_pages} pages (possible cursor loop).")
        if on_progress:
            on_progress(f"Fetching page {page}…  ({len(products)} loaded so far)")

        items, next_page_info = _rest_get_products_page(store, token, page_info=page_info, limit=250)
        if not items:
            break

        products.extend(_rest_product_to_internal(p) for p in items)
        page += 1
        if not next_page_info:
            break
        if next_page_info in seen_page_info:
            raise RuntimeError("Pagination aborted: repeated cursor detected from Shopify response.")
        seen_page_info.add(next_page_info)
        page_info = next_page_info

    return products


def fetch_products_page(
    store: str,
    token: str,
    page_number: int,
    on_progress: Callable[[str], None] | None = None,
) -> tuple[list[dict], int, bool]:
    """Fetch exactly one logical page (250 items) via REST cursor pagination."""
    if page_number < 1:
        raise ValueError("page_number must be >= 1")

    page_info: str | None = None
    seen_page_info: set[str] = set()
    current = 1
    max_pages = max(page_number + 5, 50)
    while True:
        if current > max_pages:
            raise RuntimeError(f"Pagination aborted: exceeded {max_pages} pages while seeking page {page_number}.")
        if on_progress:
            on_progress(f"Fetching page {current}…")

        items, next_page_info = _rest_get_products_page(store, token, page_info=page_info, limit=250)
        products = [_rest_product_to_internal(p) for p in items]

        if current == page_number:
            return products, current, bool(next_page_info)

        if not items or not next_page_info:
            break
        if next_page_info in seen_page_info:
            raise RuntimeError("Pagination aborted: repeated cursor detected from Shopify response.")
        seen_page_info.add(next_page_info)
        page_info = next_page_info
        current += 1

    return [], current, False


def fetch_products_range(
    store: str,
    token: str,
    from_page: int,
    to_page: int,
    on_progress: Callable[[str], None] | None = None,
) -> tuple[list[dict], int, int, bool]:
    """Fetch products from page range [from_page..to_page] via REST cursor pagination.

    Returns (products, actual_start_page, actual_end_page, has_next_after_end).
    """
    if from_page < 1 or to_page < 1:
        raise ValueError("from_page and to_page must be >= 1")
    if from_page > to_page:
        raise ValueError("from_page must be <= to_page")

    page_info: str | None = None
    seen_page_info: set[str] = set()
    current = 1
    out: list[dict] = []
    actual_start = 0
    actual_end = 0
    max_pages = max(to_page + 5, 50)

    while True:
        if current > max_pages:
            raise RuntimeError(f"Pagination aborted: exceeded {max_pages} pages while seeking range {from_page}-{to_page}.")
        if on_progress:
            on_progress(f"Fetching page {current}…")

        items, next_page_info = _rest_get_products_page(store, token, page_info=page_info, limit=250)
        if not items:
            break

        if from_page <= current <= to_page:
            if actual_start == 0:
                actual_start = current
            actual_end = current
            out.extend(_rest_product_to_internal(p) for p in items)

        if current >= to_page:
            return out, (actual_start or current), (actual_end or current), bool(next_page_info)

        if not next_page_info:
            break

        if next_page_info in seen_page_info:
            raise RuntimeError("Pagination aborted: repeated cursor detected from Shopify response.")
        seen_page_info.add(next_page_info)

        page_info = next_page_info
        current += 1

    last_page = max(0, current)
    return out, (actual_start or last_page), (actual_end or last_page), False


def _collect_metafield_keys_via_index_endpoint(
    store: str,
    token: str,
    owner: str,
    prefix: str,
    max_pages: int = 40,
) -> set[str]:
    """Collect metafield keys from /metafields.json index endpoint with cursor pagination."""
    results: set[str] = set()
    page_info: str | None = None
    seen_page_info: set[str] = set()
    page = 1

    while page <= max_pages:
        url = f"{_rest_base_url(store)}/metafields.json"
        if page_info:
            params = {"limit": 250, "page_info": page_info}
        else:
            params = {"limit": 250, "metafield[owner_resource]": owner}

        resp = requests.get(url, headers=_headers(token), params=params, timeout=30)
        if not resp.ok:
            break

        body = resp.json()
        items = body.get("metafields", []) if isinstance(body, dict) else []
        if not items:
            break

        for mf in items:
            if not isinstance(mf, dict):
                continue
            ns = str(mf.get("namespace", "")).strip()
            key = str(mf.get("key", "")).strip()
            owner_res = str(mf.get("owner_resource", "")).strip().lower()
            if ns and key and (not owner_res or owner_res == owner):
                results.add(f"{prefix}.{ns}.{key}")

        next_page_info = _parse_next_page_info(resp.headers.get("Link", ""))
        if not next_page_info:
            break
        if next_page_info in seen_page_info:
            logger.warning("Metafield index pagination loop detected; stopping discovery.")
            break

        seen_page_info.add(next_page_info)
        page_info = next_page_info
        page += 1

    return results


def _collect_metafields_for_resource(
    url: str,
    token: str,
) -> list[dict]:
    """Fetch all metafields for a specific product/variant resource with cursor pagination."""
    out: list[dict] = []
    page_info: str | None = None
    seen_page_info: set[str] = set()
    while True:
        if page_info:
            params = {"limit": 250, "page_info": page_info}
        else:
            params = {"limit": 250}
        resp = requests.get(url, headers=_headers(token), params=params, timeout=30)
        if not resp.ok:
            break
        body = resp.json()
        items = body.get("metafields", []) if isinstance(body, dict) else []
        if not items:
            break
        out.extend(items)
        next_page_info = _parse_next_page_info(resp.headers.get("Link", ""))
        if not next_page_info:
            break
        if next_page_info in seen_page_info:
            logger.warning("Resource metafields pagination loop detected; stopping resource scan.")
            break
        seen_page_info.add(next_page_info)
        page_info = next_page_info
    return out


def _collect_metafield_keys_via_resource_scan(
    store: str,
    token: str,
) -> set[str]:
    """Fallback: full scan product/variant resources and collect metafield namespace.key paths."""
    results: set[str] = set()
    page_info: str | None = None
    seen_page_info: set[str] = set()
    page = 1
    max_pages = 2000

    while page <= max_pages:
        items, next_page_info = _rest_get_products_page(store, token, page_info=page_info, limit=250)
        if not items:
            break

        for p in items:
            pid = str(p.get("id", "")).strip()
            if not pid:
                continue

            # Product metafields
            try:
                prod_url = f"{_rest_base_url(store)}/products/{quote(pid)}/metafields.json"
                for mf in _collect_metafields_for_resource(prod_url, token):
                    if not isinstance(mf, dict):
                        continue
                    ns = str(mf.get("namespace", "")).strip()
                    key = str(mf.get("key", "")).strip()
                    if ns and key:
                        results.add(f"metafields.{ns}.{key}")
            except Exception:
                pass

            # Variant metafields
            variants = p.get("variants", []) or []
            if isinstance(variants, list):
                for v in variants:
                    vid = str((v or {}).get("id", "")).strip() if isinstance(v, dict) else ""
                    if not vid:
                        continue
                    try:
                        var_url = f"{_rest_base_url(store)}/variants/{quote(vid)}/metafields.json"
                        for mf in _collect_metafields_for_resource(var_url, token):
                            if not isinstance(mf, dict):
                                continue
                            ns = str(mf.get("namespace", "")).strip()
                            key = str(mf.get("key", "")).strip()
                            if ns and key:
                                results.add(f"variants.0.metafields.{ns}.{key}")
                    except Exception:
                        pass

        if not next_page_info:
            break
        if next_page_info in seen_page_info:
            logger.warning("Product sampling pagination loop detected; stopping metafield discovery.")
            break
        seen_page_info.add(next_page_info)
        page_info = next_page_info
        page += 1

    return results


def fetch_metafield_definitions(store: str, token: str) -> list[str]:
    """Fast discovery: infer fields from product #1 on page 1, plus its own metafields."""

    def _flatten_paths(obj: object, base: str = "") -> set[str]:
        out: set[str] = set()
        if isinstance(obj, dict):
            for k, v in obj.items():
                key = f"{base}.{k}" if base else str(k)
                out.add(key)
                out.update(_flatten_paths(v, key))
        elif isinstance(obj, list) and obj:
            idx_key = f"{base}.0" if base else "0"
            out.add(idx_key)
            out.update(_flatten_paths(obj[0], idx_key))
        return out

    results: set[str] = set()
    # Fetch first 10 products to get a representative sample of standard field paths
    items, _ = _rest_get_products_page(store, token, page_info=None, limit=10)
    if not items:
        return []

    p = items[0]
    internal = _rest_product_to_internal(p)
    results.update(_flatten_paths(internal))

    base = _rest_base_url(store)
    hdrs = _headers(token)

    for p in items:
        pid = str(p.get("id", "")).strip()
        if pid:
            try:
                r_prod = requests.get(
                    f"{base}/products/{quote(pid)}/metafields.json",
                    headers=hdrs,
                    params={"limit": 250},
                    timeout=30,
                )
                if r_prod.ok:
                    body = r_prod.json()
                    for mf in body.get("metafields", []) if isinstance(body, dict) else []:
                        if not isinstance(mf, dict):
                            continue
                        ns = str(mf.get("namespace", "")).strip()
                        key = str(mf.get("key", "")).strip()
                        if ns and key:
                            results.add(f"metafields.{ns}.{key}")
            except Exception:
                pass

        variants = p.get("variants", []) or []
        if isinstance(variants, list) and variants:
            v0 = variants[0] if isinstance(variants[0], dict) else {}
            vid = str(v0.get("id", "")).strip()
            if vid:
                try:
                    r_var = requests.get(
                        f"{base}/variants/{quote(vid)}/metafields.json",
                        headers=hdrs,
                        params={"limit": 250},
                        timeout=30,
                    )
                    if r_var.ok:
                        body = r_var.json()
                        for mf in body.get("metafields", []) if isinstance(body, dict) else []:
                            if not isinstance(mf, dict):
                                continue
                            ns = str(mf.get("namespace", "")).strip()
                            key = str(mf.get("key", "")).strip()
                            if ns and key:
                                results.add(f"variants.0.metafields.{ns}.{key}")
                except Exception:
                    pass

    # Use GraphQL metafield definitions to discover ALL defined fields regardless of value
    try:
        gql_url = f"https://{store}/admin/api/{API_VER}/graphql.json"
        for owner_type, prefix in [("PRODUCT", "metafields"), ("PRODUCTVARIANT", "variants.0.metafields")]:
            cursor: str | None = None
            while True:
                after = f', after: "{cursor}"' if cursor else ""
                query = f"""
                {{
                  metafieldDefinitions(ownerType: {owner_type}, first: 250{after}) {{
                    edges {{
                      node {{ namespace key }}
                      cursor
                    }}
                    pageInfo {{ hasNextPage }}
                  }}
                }}
                """
                resp = requests.post(gql_url, headers=hdrs, json={"query": query}, timeout=30)
                if not resp.ok:
                    break
                data = resp.json().get("data", {}) or {}
                conn = data.get("metafieldDefinitions", {}) or {}
                edges = conn.get("edges", []) or []
                for edge in edges:
                    node = edge.get("node", {}) or {}
                    ns = str(node.get("namespace", "")).strip()
                    key = str(node.get("key", "")).strip()
                    if ns and key:
                        results.add(f"{prefix}.{ns}.{key}")
                    cursor = edge.get("cursor")
                if not conn.get("pageInfo", {}).get("hasNextPage"):
                    break
    except Exception:
        pass

    # Also scan store-wide metafield index to catch fields not on the first product
    try:
        results.update(_collect_metafield_keys_via_index_endpoint(store, token, "product", "metafields"))
    except Exception:
        pass
    try:
        results.update(
            f"variants.0.{k}"
            for k in _collect_metafield_keys_via_index_endpoint(store, token, "variant", "metafields")
        )
    except Exception:
        pass

    return sorted(results)


def enrich_products_with_metafields(
    products: list[dict],
    store: str,
    token: str,
    fields: list[str],
    on_progress: Callable[[str], None] | None = None,
) -> None:
    """Attach metafield values into each product dict in-place.

    For every product, fetch product-level and variant-level metafields
    that match the namespace.key pairs found in *fields*.

    After this call:
      p["metafields"]["namespace"]["key"] = value          (product metafield)
      p["variants"][i]["metafields"]["namespace"]["key"]   (variant metafield)
    """
    need_product_mf = any(
        f.startswith("metafields.") and not f.startswith("variants.") for f in fields
    )
    need_variant_mf = any(f.startswith("variants.") and ".metafields." in f for f in fields)

    if not need_product_mf and not need_variant_mf:
        return

    base = _rest_base_url(store)
    hdrs = _headers(token)
    total = len(products)

    for idx, p in enumerate(products):
        pid = str(p.get("id", "")).strip()
        if on_progress and idx % 10 == 0:
            on_progress(f"Fetching metafields {idx + 1}/{total}…")

        if need_product_mf and pid:
            try:
                resp = requests.get(
                    f"{base}/products/{quote(pid)}/metafields.json",
                    headers=hdrs,
                    params={"limit": 250},
                    timeout=30,
                )
                if resp.ok:
                    mf_dict: dict = p.setdefault("metafields", {})
                    for mf in resp.json().get("metafields", []):
                        if not isinstance(mf, dict):
                            continue
                        ns = str(mf.get("namespace", "")).strip()
                        key = str(mf.get("key", "")).strip()
                        val = mf.get("value", "")
                        if ns and key:
                            mf_dict.setdefault(ns, {})[key] = val
            except Exception:
                pass

        if need_variant_mf:
            variants = p.get("variants") or []
            for v in variants:
                if not isinstance(v, dict):
                    continue
                vid = str(v.get("id", "")).strip()
                if not vid:
                    continue
                try:
                    resp = requests.get(
                        f"{base}/variants/{quote(vid)}/metafields.json",
                        headers=hdrs,
                        params={"limit": 250},
                        timeout=30,
                    )
                    if resp.ok:
                        vmf_dict: dict = v.setdefault("metafields", {})
                        for mf in resp.json().get("metafields", []):
                            if not isinstance(mf, dict):
                                continue
                            ns = str(mf.get("namespace", "")).strip()
                            key = str(mf.get("key", "")).strip()
                            val = mf.get("value", "")
                            if ns and key:
                                vmf_dict.setdefault(ns, {})[key] = val
                except Exception:
                    pass

    if on_progress:
        on_progress(f"Metafields fetched for {total} products.")


# ──────────────────────────────────────────────────────────
#  Write operations
# ──────────────────────────────────────────────────────────
def update_product_api(
    store: str,
    token: str,
    product_id: str,
    payload: dict,
    max_retries: int = 5,
    stats: dict | None = None,
    on_backoff: Callable[[float, str], None] | None = None,
) -> tuple[bool, int, str]:
    """REST product update. Returns (ok, status_code_like, error_message)."""

    def _count_request() -> None:
        if stats is None:
            return
        stats["requests"] = int(stats.get("requests", 0)) + 1

    def _infer_metafield_type(value: object) -> str:
        if isinstance(value, bool):
            return "boolean"
        s = str(value).strip()
        if re.fullmatch(r"-?\d+", s):
            return "number_integer"
        if re.fullmatch(r"-?\d+\.\d+", s):
            return "number_decimal"
        return "single_line_text_field"

    def _extract_metafield_items(mf_obj: object) -> list[tuple[str, str, object]]:
        out: list[tuple[str, str, object]] = []
        if not isinstance(mf_obj, dict):
            return out
        for ns, kv in mf_obj.items():
            ns_s = str(ns).strip()
            if not ns_s or not isinstance(kv, dict):
                continue
            for key, value in kv.items():
                key_s = str(key).strip()
                if not key_s or value in (None, ""):
                    continue
                out.append((ns_s, key_s, value))
        return out

    def _retry_after_seconds(resp: requests.Response) -> float | None:
        raw = str(resp.headers.get("Retry-After", "")).strip()
        if not raw:
            return None
        try:
            v = float(raw)
            return v if v >= 0 else None
        except Exception:
            return None

    def _sleep_with_backoff(seconds: float, reason: str) -> None:
        wait_secs = max(0.0, float(seconds or 0.0))
        if on_backoff is not None:
            try:
                on_backoff(wait_secs, reason)
            except Exception:
                pass
        time.sleep(wait_secs)

    def _upsert_owner_metafield(owner_url: str, token_val: str, ns: str, key: str, value: object) -> tuple[bool, int, str]:
        owner_resource = "variant" if "/variants/" in owner_url else "product"
        cache_key = (owner_resource, ns, key)
        cached = _METAFIELD_VERIFY_CACHE.get(cache_key)
        inferred_type = _infer_metafield_type(value)

        # Fast path after first verification: try POST directly.
        if cached:
            post_type = cached.get("type") or inferred_type
            _count_request()
            resp_post_fast = requests.post(
                owner_url,
                headers=_headers(token_val),
                json={
                    "metafield": {
                        "namespace": ns,
                        "key": key,
                        "value": str(value),
                        "type": post_type,
                    }
                },
                timeout=30,
            )
            if resp_post_fast.ok:
                return True, 200, ""
            # If key already exists, fallback to lookup+update for this owner.
            if resp_post_fast.status_code not in {409, 422}:
                return False, resp_post_fast.status_code, f"HTTP {resp_post_fast.status_code}: {resp_post_fast.text[:300]}"

        # Try to fetch existing metafield first, so we can preserve type.
        _count_request()
        resp_get = requests.get(
            owner_url,
            headers=_headers(token_val),
            params={"namespace": ns, "key": key, "limit": 1},
            timeout=30,
        )
        if not resp_get.ok:
            return False, resp_get.status_code, f"HTTP {resp_get.status_code}: {resp_get.text[:300]}"

        body = resp_get.json()
        items = body.get("metafields", []) if isinstance(body, dict) else []
        if items:
            mf = items[0] if isinstance(items[0], dict) else {}
            mf_id = str(mf.get("id", "")).strip()
            mf_type = str(mf.get("type", "")).strip() or _infer_metafield_type(value)
            if not mf_id:
                return False, 0, "Invalid metafield id from Shopify"

            url_put = f"{_rest_base_url(store)}/metafields/{quote(mf_id)}.json"
            _count_request()
            resp_put = requests.put(
                url_put,
                headers=_headers(token_val),
                json={"metafield": {"id": mf_id, "value": str(value), "type": mf_type}},
                timeout=30,
            )
            if not resp_put.ok:
                return False, resp_put.status_code, f"HTTP {resp_put.status_code}: {resp_put.text[:300]}"
            _METAFIELD_VERIFY_CACHE[cache_key] = {"type": mf_type}
            return True, 200, ""

        # Create new metafield if not found.
        _count_request()
        resp_post = requests.post(
            owner_url,
            headers=_headers(token_val),
            json={
                "metafield": {
                    "namespace": ns,
                    "key": key,
                    "value": str(value),
                    "type": inferred_type,
                }
            },
            timeout=30,
        )
        if not resp_post.ok:
            return False, resp_post.status_code, f"HTTP {resp_post.status_code}: {resp_post.text[:300]}"
        _METAFIELD_VERIFY_CACHE[cache_key] = {"type": inferred_type}
        return True, 200, ""

    wait = 1
    for attempt in range(max_retries):
        try:
            prod = payload.get("product", {}) if isinstance(payload, dict) else {}
            pid = _gid_tail(str(product_id))

            # 1) top-level product update (pass through selected fields as-is)
            product_input: dict = {"id": pid}
            if isinstance(prod, dict):
                for key, value in prod.items():
                    if key in {"id", "variants", "images", "metafields"}:
                        continue
                    if value in (None, ""):
                        continue
                    product_input[key] = value

            if len(product_input) > 1:
                url_product = f"{_rest_base_url(store)}/products/{quote(str(pid))}.json"
                _count_request()
                resp_prod = requests.put(
                    url_product,
                    headers=_headers(token),
                    json={"product": product_input},
                    timeout=30,
                )
                if not resp_prod.ok:
                    msg = f"HTTP {resp_prod.status_code}: {resp_prod.text[:300]}"
                    if resp_prod.status_code == 429 or "throttle" in msg.lower():
                        retry_after = _retry_after_seconds(resp_prod)
                        sleep_for = retry_after if retry_after is not None else wait
                        _sleep_with_backoff(sleep_for, "product throttled")
                        wait = min(wait * 2, 32)
                        continue
                    return False, resp_prod.status_code, msg

            # 2) variants update (best-effort via /variants/{id}.json)
            variants = prod.get("variants") if isinstance(prod, dict) else None
            if isinstance(variants, list) and variants:
                for v in variants:
                    if not isinstance(v, dict):
                        continue
                    vid = _gid_tail(str(v.get("id", "")).strip())
                    if not vid:
                        continue
                    one: dict = {"id": vid}
                    for key, value in v.items():
                        if key in {"id", "metafields"}:
                            continue
                        if value in (None, ""):
                            continue
                        one[key] = value
                    if len(one) <= 1:
                        continue
                    url_var = f"{_rest_base_url(store)}/variants/{quote(str(vid))}.json"
                    _count_request()
                    resp_var = requests.put(
                        url_var,
                        headers=_headers(token),
                        json={"variant": one},
                        timeout=30,
                    )
                    if not resp_var.ok:
                        msg = f"HTTP {resp_var.status_code}: {resp_var.text[:300]}"
                        if resp_var.status_code == 429 or "throttle" in msg.lower():
                            retry_after = _retry_after_seconds(resp_var)
                            sleep_for = retry_after if retry_after is not None else wait
                            _sleep_with_backoff(sleep_for, "variant throttled")
                            wait = min(wait * 2, 32)
                            continue
                        return False, resp_var.status_code, msg

                    # 2b) variant metafields upsert
                    for ns, key, value in _extract_metafield_items(v.get("metafields")):
                        var_meta_url = f"{_rest_base_url(store)}/variants/{quote(str(vid))}/metafields.json"
                        ok_mf, code_mf, msg_mf = _upsert_owner_metafield(var_meta_url, token, ns, key, value)
                        if not ok_mf:
                            if code_mf == 429 or "throttle" in msg_mf.lower():
                                _sleep_with_backoff(wait, "variant metafield throttled")
                                wait = min(wait * 2, 32)
                                continue
                            return False, code_mf, msg_mf

            # 2c) product metafields upsert
            for ns, key, value in _extract_metafield_items(prod.get("metafields") if isinstance(prod, dict) else None):
                prod_meta_url = f"{_rest_base_url(store)}/products/{quote(str(pid))}/metafields.json"
                ok_mf, code_mf, msg_mf = _upsert_owner_metafield(prod_meta_url, token, ns, key, value)
                if not ok_mf:
                    if code_mf == 429 or "throttle" in msg_mf.lower():
                        _sleep_with_backoff(wait, "product metafield throttled")
                        wait = min(wait * 2, 32)
                        continue
                    return False, code_mf, msg_mf

            # 3) images add via /products/{id}/images.json
            images = prod.get("images") if isinstance(prod, dict) else None
            if isinstance(images, list) and images:
                for img in images:
                    if not isinstance(img, dict):
                        continue
                    src = str(img.get("src", "")).strip()
                    attachment = img.get("attachment")
                    image_payload: dict = {}
                    if src:
                        image_payload["src"] = src
                    elif attachment:
                        image_payload["attachment"] = attachment
                    else:
                        continue
                    alt = str(img.get("alt", "")).strip()
                    if alt:
                        image_payload["alt"] = alt

                    url_img = f"{_rest_base_url(store)}/products/{quote(str(pid))}/images.json"
                    _count_request()
                    resp_img = requests.post(
                        url_img,
                        headers=_headers(token),
                        json={"image": image_payload},
                        timeout=45,
                    )
                    if not resp_img.ok:
                        msg = f"HTTP {resp_img.status_code}: {resp_img.text[:300]}"
                        if resp_img.status_code == 429 or "throttle" in msg.lower():
                            retry_after = _retry_after_seconds(resp_img)
                            sleep_for = retry_after if retry_after is not None else wait
                            _sleep_with_backoff(sleep_for, "image throttled")
                            wait = min(wait * 2, 32)
                            continue
                        return False, resp_img.status_code, msg

            return True, 200, ""
        except requests.RequestException as exc:
            _sleep_with_backoff(wait, f"network error: {exc}")
            wait = min(wait * 2, 32)
        except Exception as exc:
            msg = str(exc)
            if "429" in msg or "throttle" in msg.lower():
                _sleep_with_backoff(wait, "generic throttled error")
                wait = min(wait * 2, 32)
                continue
            return False, 0, msg[:500]
    return False, 0, f"Max retries exceeded ({max_retries})"
