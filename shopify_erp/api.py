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


def fetch_metafield_definitions(store: str, token: str) -> list[str]:
    """Return flat dot-notation paths for all metafield definitions via REST."""
    results: list[str] = []
    for owner, prefix in [("product", "metafields"), ("variant", "variants.0.metafields")]:
        url = f"{_rest_base_url(store)}/metafield_definitions.json"
        params = {"owner_resource": owner, "limit": 250}
        try:
            resp = requests.get(
                url,
                headers=_headers(token),
                params=params,
                timeout=30,
            )
            if not resp.ok:
                # REST metafield definitions endpoint can be unavailable on some API versions.
                logger.info(f"Metafield definitions via REST unavailable for {owner}: HTTP {resp.status_code}")
                continue

            body = resp.json()
            defs = body.get("metafield_definitions", []) if isinstance(body, dict) else []
            for n in defs:
                ns = n.get("namespace", "")
                key = n.get("key", "")
                if ns and key:
                    results.append(f"{prefix}.{ns}.{key}")
        except Exception as exc:
            logger.info(f"Metafield definitions via REST exception for {owner}: {exc}")

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
    """REST product update. Returns (ok, status_code_like, error_message)."""
    wait = 1
    for attempt in range(max_retries):
        try:
            prod = payload.get("product", {}) if isinstance(payload, dict) else {}
            pid = _gid_tail(str(product_id))

            # 1) top-level product update
            product_input: dict = {"id": pid}
            top_fields = ["title", "body_html", "vendor", "product_type", "handle", "tags", "status"]
            for key in top_fields:
                if key in prod and prod[key] not in (None, ""):
                    product_input[key] = str(prod[key])

            if len(product_input) > 1:
                url_product = f"{_rest_base_url(store)}/products/{quote(str(pid))}.json"
                resp_prod = requests.put(
                    url_product,
                    headers=_headers(token),
                    json={"product": product_input},
                    timeout=30,
                )
                if not resp_prod.ok:
                    msg = f"HTTP {resp_prod.status_code}: {resp_prod.text[:300]}"
                    if resp_prod.status_code == 429 or "throttle" in msg.lower():
                        time.sleep(wait)
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
                    if v.get("sku") not in (None, ""):
                        one["sku"] = str(v.get("sku"))
                    if v.get("price") not in (None, ""):
                        one["price"] = str(v.get("price"))
                    if v.get("compare_at_price") not in (None, ""):
                        one["compare_at_price"] = str(v.get("compare_at_price"))
                    if v.get("barcode") not in (None, ""):
                        one["barcode"] = str(v.get("barcode"))
                    if v.get("taxable") not in (None, ""):
                        one["taxable"] = bool(v.get("taxable"))
                    if len(one) <= 1:
                        continue
                    url_var = f"{_rest_base_url(store)}/variants/{quote(str(vid))}.json"
                    resp_var = requests.put(
                        url_var,
                        headers=_headers(token),
                        json={"variant": one},
                        timeout=30,
                    )
                    if not resp_var.ok:
                        msg = f"HTTP {resp_var.status_code}: {resp_var.text[:300]}"
                        if resp_var.status_code == 429 or "throttle" in msg.lower():
                            time.sleep(wait)
                            wait = min(wait * 2, 32)
                            continue
                        return False, resp_var.status_code, msg

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
                    resp_img = requests.post(
                        url_img,
                        headers=_headers(token),
                        json={"image": image_payload},
                        timeout=45,
                    )
                    if not resp_img.ok:
                        msg = f"HTTP {resp_img.status_code}: {resp_img.text[:300]}"
                        if resp_img.status_code == 429 or "throttle" in msg.lower():
                            time.sleep(wait)
                            wait = min(wait * 2, 32)
                            continue
                        return False, resp_img.status_code, msg

            return True, 200, ""
        except requests.RequestException as exc:
            time.sleep(wait)
            wait = min(wait * 2, 32)
        except Exception as exc:
            msg = str(exc)
            if "429" in msg or "throttle" in msg.lower():
                time.sleep(wait)
                wait = min(wait * 2, 32)
                continue
            return False, 0, msg[:500]
    return False, 0, f"Max retries exceeded ({max_retries})"
