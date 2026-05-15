"""Shopify API helpers (REST-first for product flows)."""

from __future__ import annotations

import mimetypes
import re
import time
import logging
from pathlib import Path
from typing import Callable
from urllib.parse import quote, unquote

import requests

from .constants import API_VER
from .logger import append_work_table_row

logger = logging.getLogger(__name__)

# Fast-path cache for metafield uploads:
# verify once (first owner/first SKU), then reuse known type/strategy for next rows.
_METAFIELD_VERIFY_CACHE: dict[tuple[str, str, str], dict[str, str]] = {}
_METAFIELD_DEFINITION_TYPE_CACHE: dict[tuple[str, str, str], str] = {}


def _short_work_text(value: object, limit: int = 220) -> str:
    text = str(value or "").replace("\r", " ").replace("\n", " ").strip()
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def _graphql_operation_name(query: str) -> str:
    match = re.search(r"\b(query|mutation)\s+([A-Za-z0-9_]+)", str(query or ""))
    if match:
        return match.group(2)
    return "graphql"


def _log_api_table_row(
    area: str,
    operation: str,
    method: str,
    endpoint: str,
    product_id: str = "",
    variant_id: str = "",
    field_name: str = "",
    status_code: int | str = "",
    outcome: str = "",
    details: str = "",
) -> None:
    append_work_table_row(
        {
            "area": area,
            "operation": operation,
            "method": method,
            "endpoint": endpoint,
            "product_id": product_id,
            "variant_id": variant_id,
            "field_name": field_name,
            "status_code": status_code,
            "outcome": outcome,
            "details": _short_work_text(details),
        }
    )


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


def _graphql_url(store: str) -> str:
    return f"https://{store}/admin/api/{API_VER}/graphql.json"


def _graphql_post(store: str, token: str, query: str, variables: dict | None = None, timeout: int = 45) -> dict:
    payload: dict[str, object] = {"query": query}
    if variables is not None:
        payload["variables"] = variables
    operation_name = _graphql_operation_name(query)
    try:
        resp = requests.post(_graphql_url(store), headers=_headers(token), json=payload, timeout=timeout)
    except requests.RequestException as exc:
        _log_api_table_row(
            area="graphql",
            operation=operation_name,
            method="POST",
            endpoint=_graphql_url(store),
            status_code=0,
            outcome="EXCEPTION",
            details=str(exc),
        )
        raise
    if not resp.ok:
        _log_api_table_row(
            area="graphql",
            operation=operation_name,
            method="POST",
            endpoint=_graphql_url(store),
            status_code=resp.status_code,
            outcome="FAIL",
            details=resp.text[:300],
        )
        raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:300]}")
    body = resp.json() if resp.content else {}
    errors = body.get("errors", []) if isinstance(body, dict) else []
    if errors:
        first = errors[0] if isinstance(errors[0], dict) else {}
        _log_api_table_row(
            area="graphql",
            operation=operation_name,
            method="POST",
            endpoint=_graphql_url(store),
            status_code=resp.status_code,
            outcome="GRAPHQL_ERROR",
            details=str(first.get("message", "GraphQL request failed")),
        )
        raise RuntimeError(str(first.get("message", "GraphQL request failed")))
    _log_api_table_row(
        area="graphql",
        operation=operation_name,
        method="POST",
        endpoint=_graphql_url(store),
        status_code=resp.status_code,
        outcome="OK",
        details=f"variables={sorted((variables or {}).keys())}",
    )
    return body.get("data", {}) if isinstance(body, dict) else {}


def get_metafield_definition_type(store: str, token: str, owner_type: str, namespace: str, key: str) -> str:
        cache_key = (owner_type, namespace, key)
        cached = _METAFIELD_DEFINITION_TYPE_CACHE.get(cache_key)
        if cached is not None:
                return cached

        query = """
        query MetafieldDefinitionType($ownerType: MetafieldOwnerType!, $namespace: String!, $key: String!) {
            metafieldDefinitions(ownerType: $ownerType, namespace: $namespace, key: $key, first: 1) {
                nodes {
                    type {
                        name
                    }
                }
            }
        }
        """
        data = _graphql_post(
                store,
                token,
                query,
                variables={"ownerType": owner_type, "namespace": namespace, "key": key},
        )
        nodes = (((data or {}).get("metafieldDefinitions") or {}).get("nodes") or [])
        type_name = ""
        if nodes:
                first = nodes[0] if isinstance(nodes[0], dict) else {}
                type_name = str(((first.get("type") or {}).get("name") or "")).strip()
        _METAFIELD_DEFINITION_TYPE_CACHE[cache_key] = type_name
        return type_name


def _extract_shopify_file_url(file_node: dict) -> str:
        if not isinstance(file_node, dict):
                return ""
        image = file_node.get("image") or {}
        if isinstance(image, dict):
                image_url = str(image.get("url", "")).strip()
                if image_url:
                        return image_url
        direct_url = str(file_node.get("url", "")).strip()
        if direct_url:
                return direct_url
        preview = file_node.get("preview") or {}
        if isinstance(preview, dict):
                preview_image = preview.get("image") or {}
                if isinstance(preview_image, dict):
                        preview_url = str(preview_image.get("url", "")).strip()
                        if preview_url:
                                return preview_url
        return ""


def upload_file_to_shopify_files(store: str, token: str, file_path: str | Path, alt: str = "") -> tuple[bool, str, str, str]:
    path = Path(file_path)
    if not path.is_file():
        _log_api_table_row(
            area="files",
            operation="upload_file_to_shopify_files",
            method="POST",
            endpoint="shopify-files",
            status_code=0,
            outcome="FAIL",
            details=f"File not found: {path}",
        )
        return False, "", "", f"File not found: {path}"

        mime_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        content_type = "IMAGE" if mime_type.startswith("image/") else "FILE"

        query_stage = """
        mutation CreateStagedUpload($input: [StagedUploadInput!]!) {
            stagedUploadsCreate(input: $input) {
                stagedTargets {
                    url
                    resourceUrl
                    parameters {
                        name
                        value
                    }
                }
                userErrors {
                    field
                    message
                }
            }
        }
        """
        data_stage = _graphql_post(
                store,
                token,
                query_stage,
                variables={
                        "input": [
                                {
                                        "filename": path.name,
                                        "mimeType": mime_type,
                                        "httpMethod": "POST",
                                        "resource": content_type,
                                }
                        ]
                },
                timeout=60,
        )
        stage_payload = (data_stage or {}).get("stagedUploadsCreate") or {}
        stage_errors = stage_payload.get("userErrors") or []
        if stage_errors:
                first_error = stage_errors[0] if isinstance(stage_errors[0], dict) else {}
                return False, "", "", str(first_error.get("message", "stagedUploadsCreate failed"))
        staged_targets = stage_payload.get("stagedTargets") or []
        if not staged_targets:
                return False, "", "", "No staged upload target returned"

        target = staged_targets[0] if isinstance(staged_targets[0], dict) else {}
        upload_url = str(target.get("url", "")).strip()
        resource_url = str(target.get("resourceUrl", "")).strip()
        parameters = target.get("parameters") or []
        if not upload_url or not resource_url:
                return False, "", "", "Invalid staged upload target returned"

        form_data: list[tuple[str, str]] = []
        for item in parameters:
                if not isinstance(item, dict):
                        continue
                name = str(item.get("name", "")).strip()
                value = str(item.get("value", ""))
                if name:
                        form_data.append((name, value))

        with path.open("rb") as fh:
                resp_upload = requests.post(
                        upload_url,
                        data=form_data,
                        files={"file": (path.name, fh, mime_type)},
                        timeout=120,
                )
        if not resp_upload.ok:
            _log_api_table_row(
                area="files",
                operation="staged_upload_post",
                method="POST",
                endpoint=upload_url,
                field_name=path.name,
                status_code=resp_upload.status_code,
                outcome="FAIL",
                details=resp_upload.text[:300],
            )
            return False, "", "", f"HTTP {resp_upload.status_code}: {resp_upload.text[:300]}"
        _log_api_table_row(
            area="files",
            operation="staged_upload_post",
            method="POST",
            endpoint=upload_url,
            field_name=path.name,
            status_code=resp_upload.status_code,
            outcome="OK",
            details=f"resource={content_type}",
        )

        query_create = """
        mutation CreateFile($files: [FileCreateInput!]!) {
            fileCreate(files: $files) {
                files {
                    id
                    fileStatus
                    preview {
                        image {
                            url
                        }
                    }
                    ... on MediaImage {
                        image {
                            url
                        }
                    }
                    ... on GenericFile {
                        url
                    }
                }
                userErrors {
                    field
                    message
                }
            }
        }
        """
        data_create = _graphql_post(
                store,
                token,
                query_create,
                variables={
                        "files": [
                                {
                                        "alt": alt,
                                        "contentType": content_type,
                                        "originalSource": resource_url,
                                }
                        ]
                },
                timeout=60,
        )
        create_payload = (data_create or {}).get("fileCreate") or {}
        create_errors = create_payload.get("userErrors") or []
        if create_errors:
                first_error = create_errors[0] if isinstance(create_errors[0], dict) else {}
                return False, "", "", str(first_error.get("message", "fileCreate failed"))
        files = create_payload.get("files") or []
        if not files:
                return False, "", "", "No file returned from fileCreate"

        file_node = files[0] if isinstance(files[0], dict) else {}
        file_id = str(file_node.get("id", "")).strip()
        file_status = str(file_node.get("fileStatus", "")).strip().upper()
        file_url = _extract_shopify_file_url(file_node)
        _log_api_table_row(
            area="files",
            operation="file_create_result",
            method="POST",
            endpoint=_graphql_url(store),
            field_name=path.name,
            status_code=200,
            outcome="OK" if file_id else "FAIL",
            details=f"file_id={file_id or '-'} status={file_status or '-'}",
        )

        query_poll = """
        query ShopifyFileNode($id: ID!) {
            node(id: $id) {
                ... on MediaImage {
                    id
                    fileStatus
                    preview {
                        image {
                            url
                        }
                    }
                    image {
                        url
                    }
                }
                ... on GenericFile {
                    id
                    fileStatus
                    preview {
                        image {
                            url
                        }
                    }
                    url
                }
            }
        }
        """
        for _attempt in range(10):
            if file_id and file_url and file_status == "READY":
                _log_api_table_row(
                    area="files",
                    operation="file_ready",
                    method="POST",
                    endpoint=_graphql_url(store),
                    field_name=path.name,
                    status_code=200,
                    outcome="OK",
                    details=f"file_id={file_id}",
                )
                return True, file_id, file_url, ""
            if not file_id:
                break
            time.sleep(1)
            data_poll = _graphql_post(store, token, query_poll, variables={"id": file_id}, timeout=45)
            file_node = (data_poll or {}).get("node") or {}
            file_status = str(file_node.get("fileStatus", file_status)).strip().upper()
            file_url = _extract_shopify_file_url(file_node) or file_url

        if file_id and file_url:
            _log_api_table_row(
                area="files",
                operation="file_ready_partial",
                method="POST",
                endpoint=_graphql_url(store),
                field_name=path.name,
                status_code=200,
                outcome="OK",
                details=f"file_id={file_id} status={file_status}",
            )
            return True, file_id, file_url, ""
        _log_api_table_row(
            area="files",
            operation="file_ready_timeout",
            method="POST",
            endpoint=_graphql_url(store),
            field_name=path.name,
            status_code=0,
            outcome="FAIL",
            details="Shopify file upload finished without a usable file URL",
        )
        return False, file_id, file_url, "Shopify file upload finished without a usable file URL"


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
            _log_api_table_row("auth", "fetch_access_token", "POST", url, status_code=resp.status_code, outcome="FAIL", details=err_msg)
            logger.error(f"Failed to fetch token: {err_msg}")
            return False, err_msg
        body = resp.json()
        token = body.get("access_token", "").strip()
        if not token:
            _log_api_table_row("auth", "fetch_access_token", "POST", url, status_code=resp.status_code, outcome="FAIL", details="No access_token found")
            logger.error("No access_token found in token response")
            return False, "No access_token found in response."
        _log_api_table_row("auth", "fetch_access_token", "POST", url, status_code=resp.status_code, outcome="OK", details=f"store={store}")
        logger.info(f"Successfully fetched access token for {store}")
        return True, token
    except requests.RequestException as exc:
        _log_api_table_row("auth", "fetch_access_token", "POST", url, status_code=0, outcome="EXCEPTION", details=str(exc))
        logger.error(f"Token request exception: {exc}", exc_info=True)
        return False, str(exc)
    except ValueError as exc:
        _log_api_table_row("auth", "fetch_access_token", "POST", url, status_code=0, outcome="EXCEPTION", details="Token response is not valid JSON")
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
            _log_api_table_row("connection", "test_connection", "GET", url, status_code=resp.status_code, outcome="FAIL", details=resp.text[:300])
            return False, f"HTTP {resp.status_code}: {resp.text[:300]}"
        body = resp.json()
        shop_name = body.get("shop", {}).get("name", store)
        _log_api_table_row("connection", "test_connection", "GET", url, status_code=resp.status_code, outcome="OK", details=str(shop_name))
        return True, shop_name
    except requests.RequestException as exc:
        _log_api_table_row("connection", "test_connection", "GET", f"{_rest_base_url(store)}/shop.json", status_code=0, outcome="EXCEPTION", details=str(exc))
        return False, str(exc)
    except ValueError:
        _log_api_table_row("connection", "test_connection", "GET", f"{_rest_base_url(store)}/shop.json", status_code=0, outcome="EXCEPTION", details="Shop response is not valid JSON")
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


def delete_product_image_by_field(
    store: str,
    token: str,
    product_id: str,
    field_name: str,
    max_retries: int = 5,
) -> tuple[bool, int, str]:
    """Delete product gallery images addressed by images or images.N.src."""

    normalized = str(field_name or "").strip()
    delete_all = normalized == "images"
    match = re.fullmatch(r"images\.(\d+)\.src", normalized)
    if not delete_all and not match:
        return False, 0, f"Unsupported image field: {field_name}"

    pid = _gid_tail(str(product_id or "").strip())
    if not pid:
        return False, 0, "Missing product id"

    target_index = int(match.group(1)) if match else -1
    wait = 1.0

    for _attempt in range(max_retries):
        try:
            url_list = f"{_rest_base_url(store)}/products/{quote(pid)}/images.json"
            resp_list = requests.get(url_list, headers=_headers(token), timeout=30)
            if not resp_list.ok:
                msg = f"HTTP {resp_list.status_code}: {resp_list.text[:300]}"
                _log_api_table_row("image-delete", "list_product_images", "GET", url_list, product_id=pid, field_name=field_name, status_code=resp_list.status_code, outcome="FAIL", details=msg)
                if resp_list.status_code == 429 or "throttle" in msg.lower():
                    time.sleep(wait)
                    wait = min(wait * 2, 32)
                    continue
                return False, resp_list.status_code, msg

            body = resp_list.json() if resp_list.content else {}
            images = body.get("images", []) if isinstance(body, dict) else []
            if not isinstance(images, list):
                images = []
            if delete_all:
                if not images:
                    return True, 200, ""
                delete_ids = [str(img.get("id", "")).strip() for img in images if isinstance(img, dict) and str(img.get("id", "")).strip()]
                if not delete_ids:
                    return True, 200, ""
            elif target_index >= len(images):
                return True, 200, ""
            else:
                image_obj = images[target_index] if isinstance(images[target_index], dict) else {}
                image_id = str(image_obj.get("id", "")).strip()
                if not image_id:
                    return False, 0, f"Image field {field_name} does not map to a valid Shopify image id"
                delete_ids = [image_id]

            for image_id in delete_ids:
                url_delete = f"{_rest_base_url(store)}/products/{quote(pid)}/images/{quote(image_id)}.json"
                resp_delete = requests.delete(url_delete, headers=_headers(token), timeout=30)
                if resp_delete.ok or resp_delete.status_code == 404:
                    _log_api_table_row("image-delete", "delete_product_image", "DELETE", url_delete, product_id=pid, field_name=field_name, status_code=resp_delete.status_code, outcome="OK", details=f"image_id={image_id}")
                    continue

                msg = f"HTTP {resp_delete.status_code}: {resp_delete.text[:300]}"
                _log_api_table_row("image-delete", "delete_product_image", "DELETE", url_delete, product_id=pid, field_name=field_name, status_code=resp_delete.status_code, outcome="FAIL", details=msg)
                if resp_delete.status_code == 429 or "throttle" in msg.lower():
                    time.sleep(wait)
                    wait = min(wait * 2, 32)
                    break
                return False, resp_delete.status_code, msg
            else:
                return True, 200, ""
        except requests.RequestException as exc:
            time.sleep(wait)
            wait = min(wait * 2, 32)
        except Exception as exc:
            return False, 0, str(exc)[:500]

    return False, 0, f"Max retries exceeded ({max_retries})"


def clear_product_metafield(
    store: str,
    token: str,
    product_id: str,
    field_name: str,
    max_retries: int = 5,
) -> tuple[bool, int, str]:
    """Delete a product metafield addressed by metafields.namespace.key."""

    parts = str(field_name or "").strip().split(".", 2)
    if len(parts) != 3 or parts[0] != "metafields":
        return False, 0, f"Unsupported product metafield: {field_name}"

    _prefix, namespace, key = parts
    pid = _gid_tail(str(product_id or "").strip())
    if not pid:
        return False, 0, "Missing product id"

    wait = 1.0

    for _attempt in range(max_retries):
        try:
            url_list = f"{_rest_base_url(store)}/products/{quote(pid)}/metafields.json"
            resp_list = requests.get(
                url_list,
                headers=_headers(token),
                params={"namespace": namespace, "key": key, "limit": 1},
                timeout=30,
            )
            if not resp_list.ok:
                msg = f"HTTP {resp_list.status_code}: {resp_list.text[:300]}"
                _log_api_table_row("metafield-delete", "lookup_product_metafield", "GET", url_list, product_id=pid, field_name=field_name, status_code=resp_list.status_code, outcome="FAIL", details=msg)
                if resp_list.status_code == 429 or "throttle" in msg.lower():
                    time.sleep(wait)
                    wait = min(wait * 2, 32)
                    continue
                return False, resp_list.status_code, msg

            body = resp_list.json() if resp_list.content else {}
            items = body.get("metafields", []) if isinstance(body, dict) else []
            if not isinstance(items, list) or not items:
                return True, 200, ""

            first = items[0] if isinstance(items[0], dict) else {}
            metafield_id = str(first.get("id", "")).strip()
            if not metafield_id:
                return False, 0, f"Metafield {field_name} does not map to a valid Shopify metafield id"

            url_delete = f"{_rest_base_url(store)}/metafields/{quote(metafield_id)}.json"
            resp_delete = requests.delete(url_delete, headers=_headers(token), timeout=30)
            if resp_delete.ok:
                _log_api_table_row("metafield-delete", "delete_product_metafield", "DELETE", url_delete, product_id=pid, field_name=field_name, status_code=resp_delete.status_code, outcome="OK", details=f"metafield_id={metafield_id}")
                return True, 200, ""

            msg = f"HTTP {resp_delete.status_code}: {resp_delete.text[:300]}"
            if resp_delete.status_code == 404:
                _log_api_table_row("metafield-delete", "delete_product_metafield", "DELETE", url_delete, product_id=pid, field_name=field_name, status_code=resp_delete.status_code, outcome="OK", details=f"metafield_id={metafield_id}")
                return True, 200, ""
            _log_api_table_row("metafield-delete", "delete_product_metafield", "DELETE", url_delete, product_id=pid, field_name=field_name, status_code=resp_delete.status_code, outcome="FAIL", details=msg)
            if resp_delete.status_code == 429 or "throttle" in msg.lower():
                time.sleep(wait)
                wait = min(wait * 2, 32)
                continue
            return False, resp_delete.status_code, msg
        except requests.RequestException as exc:
            time.sleep(wait)
            wait = min(wait * 2, 32)
            last_error = str(exc)
        except Exception as exc:
            return False, 0, str(exc)[:500]

    return False, 0, f"Max retries exceeded ({max_retries})"


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

    def _extract_requested_pairs(prefix: str) -> set[tuple[str, str]]:
        pairs: set[tuple[str, str]] = set()
        needle = f"{prefix}."
        for f in fields:
            if not f.startswith(needle):
                continue
            tail = f[len(needle):]
            parts = tail.split(".", 2)
            if len(parts) < 2:
                continue
            ns = parts[0].strip()
            key = parts[1].strip()
            if ns and key:
                pairs.add((ns, key))
        return pairs

    if not need_product_mf and not need_variant_mf:
        return

    requested_product_pairs = _extract_requested_pairs("metafields")
    requested_variant_pairs = _extract_requested_pairs("variants.0.metafields")
    # For a small selected key set, targeted query per key is faster than pulling all metafields.
    use_targeted_product = need_product_mf and 0 < len(requested_product_pairs) <= 2
    use_targeted_variant = need_variant_mf and 0 < len(requested_variant_pairs) <= 2

    base = _rest_base_url(store)
    total = len(products)
    session = requests.Session()
    session.headers.update(_headers(token))

    try:
        for idx, p in enumerate(products):
            pid = str(p.get("id", "")).strip()
            if on_progress and idx % 10 == 0:
                on_progress(f"Fetching metafields {idx + 1}/{total}…")

            if need_product_mf and pid:
                try:
                    mf_dict: dict = p.setdefault("metafields", {})
                    if use_targeted_product:
                        for ns, key in requested_product_pairs:
                            resp = session.get(
                                f"{base}/products/{quote(pid)}/metafields.json",
                                params={"namespace": ns, "key": key, "limit": 1},
                                timeout=20,
                            )
                            if not resp.ok:
                                continue
                            items = resp.json().get("metafields", [])
                            if not items:
                                continue
                            mf = items[0] if isinstance(items[0], dict) else {}
                            val = mf.get("value", "")
                            mf_dict.setdefault(ns, {})[key] = val
                    else:
                        resp = session.get(
                            f"{base}/products/{quote(pid)}/metafields.json",
                            params={"limit": 250},
                            timeout=30,
                        )
                        if resp.ok:
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
                        vmf_dict: dict = v.setdefault("metafields", {})
                        if use_targeted_variant:
                            for ns, key in requested_variant_pairs:
                                resp = session.get(
                                    f"{base}/variants/{quote(vid)}/metafields.json",
                                    params={"namespace": ns, "key": key, "limit": 1},
                                    timeout=20,
                                )
                                if not resp.ok:
                                    continue
                                items = resp.json().get("metafields", [])
                                if not items:
                                    continue
                                mf = items[0] if isinstance(items[0], dict) else {}
                                val = mf.get("value", "")
                                vmf_dict.setdefault(ns, {})[key] = val
                        else:
                            resp = session.get(
                                f"{base}/variants/{quote(vid)}/metafields.json",
                                params={"limit": 250},
                                timeout=30,
                            )
                            if resp.ok:
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
    finally:
        try:
            session.close()
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

    def _request_logged(
        method: str,
        url: str,
        operation: str,
        *,
        variant_id: str = "",
        field_name: str = "",
        details: str = "",
        **kwargs,
    ) -> requests.Response:
        _count_request()
        try:
            resp = requests.request(method, url, **kwargs)
        except requests.RequestException as exc:
            _log_api_table_row(
                area="rest-write",
                operation=operation,
                method=method,
                endpoint=url,
                product_id=pid,
                variant_id=variant_id,
                field_name=field_name,
                status_code=0,
                outcome="EXCEPTION",
                details=details or str(exc),
            )
            raise
        _log_api_table_row(
            area="rest-write",
            operation=operation,
            method=method,
            endpoint=url,
            product_id=pid,
            variant_id=variant_id,
            field_name=field_name,
            status_code=resp.status_code,
            outcome="OK" if resp.ok else "FAIL",
            details=details or (resp.text[:300] if not resp.ok else ""),
        )
        return resp

    def _upsert_owner_metafield(owner_url: str, token_val: str, ns: str, key: str, value: object) -> tuple[bool, int, str]:
        owner_resource = "variant" if "/variants/" in owner_url else "product"
        cache_key = (owner_resource, ns, key)
        cached = _METAFIELD_VERIFY_CACHE.get(cache_key)
        inferred_type = _infer_metafield_type(value)
        owner_type = "PRODUCTVARIANT" if owner_resource == "variant" else "PRODUCT"

        # Fast path after first verification: try POST directly.
        if cached:
            post_type = cached.get("type") or inferred_type
            resp_post_fast = _request_logged(
                "POST",
                owner_url,
                f"{owner_resource}_metafield_fast_post",
                variant_id="" if owner_resource == "product" else _gid_tail(owner_url.rsplit("/", 2)[-2]),
                field_name=f"{ns}.{key}",
                details=f"type={post_type}",
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
        resp_get = _request_logged(
            "GET",
            owner_url,
            f"{owner_resource}_metafield_lookup",
            variant_id="" if owner_resource == "product" else _gid_tail(owner_url.rsplit("/", 2)[-2]),
            field_name=f"{ns}.{key}",
            details="lookup existing metafield",
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
            resp_put = _request_logged(
                "PUT",
                url_put,
                f"{owner_resource}_metafield_update",
                variant_id="" if owner_resource == "product" else _gid_tail(owner_url.rsplit("/", 2)[-2]),
                field_name=f"{ns}.{key}",
                details=f"type={mf_type}",
                headers=_headers(token_val),
                json={"metafield": {"id": mf_id, "value": str(value), "type": mf_type}},
                timeout=30,
            )
            if not resp_put.ok:
                return False, resp_put.status_code, f"HTTP {resp_put.status_code}: {resp_put.text[:300]}"
            _METAFIELD_VERIFY_CACHE[cache_key] = {"type": mf_type}
            return True, 200, ""

        # Create new metafield if not found.
        definition_type = get_metafield_definition_type(store, token_val, owner_type, ns, key)
        create_type = definition_type or inferred_type
        resp_post = _request_logged(
            "POST",
            owner_url,
            f"{owner_resource}_metafield_create",
            variant_id="" if owner_resource == "product" else _gid_tail(owner_url.rsplit("/", 2)[-2]),
            field_name=f"{ns}.{key}",
            details=f"type={create_type}",
            headers=_headers(token_val),
            json={
                "metafield": {
                    "namespace": ns,
                    "key": key,
                    "value": str(value),
                    "type": create_type,
                }
            },
            timeout=30,
        )
        if not resp_post.ok:
            return False, resp_post.status_code, f"HTTP {resp_post.status_code}: {resp_post.text[:300]}"
        _METAFIELD_VERIFY_CACHE[cache_key] = {"type": create_type}
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
                product_fields = ",".join(sorted(k for k in product_input.keys() if k != "id"))
                resp_prod = _request_logged(
                    "PUT",
                    url_product,
                    "product_update",
                    details=f"fields={product_fields}",
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
                    variant_fields = ",".join(sorted(k for k in one.keys() if k != "id"))
                    resp_var = _request_logged(
                        "PUT",
                        url_var,
                        "variant_update",
                        variant_id=str(vid),
                        details=f"fields={variant_fields}",
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
                    img_source = "src" if src else "attachment"
                    resp_img = _request_logged(
                        "POST",
                        url_img,
                        "product_image_add",
                        field_name="images",
                        details=f"source={img_source}",
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
