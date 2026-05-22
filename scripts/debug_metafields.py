"""
Simple debug script: fetch up to 10 products and print metafield custom.ecom_price

Usage:
  set SHOP_STORE=your-store.myshopify.com
  set SHOP_TOKEN=shpat_...
  python scripts/debug_metafields.py

If you prefer to inspect other fields, edit FIELDS below.
"""

from __future__ import annotations

import os
import sys
import json
from typing import List

import requests

from shopify_erp import api

FIELDS = [
    "metafields.custom.ecom_price",
    "variants.0.metafields.custom.ecom_price",
]


def main() -> int:
    store = os.environ.get("SHOP_STORE")
    token = os.environ.get("SHOP_TOKEN")
    if not store or not token:
        print("Please set environment variables SHOP_STORE and SHOP_TOKEN before running.")
        print("Example (Windows Powershell):")
        print("  $env:SHOP_STORE = 'your-store.myshopify.com'")
        print("  $env:SHOP_TOKEN = 'shpat_xxx'")
        return 2

    try:
        products, actual_page, has_next = api.fetch_products_page(store, token, 1)
    except Exception as exc:
        print("Error fetching products:", exc)
        return 3

    if not products:
        print("No products returned on page 1.")
        return 0

    # limit to 10
    products = products[:10]
    print(f"Checking {len(products)} products from {store} (page 1, up to 10)...")

    # Enrich with metafields for our FIELDS
    try:
        api.enrich_products_with_metafields(products, store, token, FIELDS, on_progress=lambda m: print(m))
    except Exception as exc:
        print("enrich_products_with_metafields raised:", exc)

    base = api._rest_base_url(store)
    headers = api._headers(token)

    for p in products:
        pid = str(p.get("id", ""))
        title = p.get("title") or p.get("name") or "(no title)"
        print("\nProduct:", pid, "-", title)

        # product-level value from enriched data
        prod_val = ""
        try:
            prod_val = p.get("metafields", {}).get("custom", {}).get("ecom_price", "")
        except Exception:
            prod_val = "<error>"
        print("  product.metafields.custom.ecom_price:", repr(prod_val))

        # For deeper inspection also call REST /products/{pid}/metafields.json
        try:
            resp = requests.get(f"{base}/products/{pid}/metafields.json", headers=headers, timeout=20)
            if resp.ok:
                body = resp.json()
                items = body.get("metafields", []) if isinstance(body, dict) else []
                matches = [mf for mf in items if mf.get("namespace") == "custom" and mf.get("key") == "ecom_price"]
                print("  REST product metafields count:", len(matches))
                if matches:
                    for mf in matches:
                        print("    ->", json.dumps(mf, ensure_ascii=False))
            else:
                print("  REST product metafields request failed status:", resp.status_code)
        except Exception as exc:
            print("  REST product metafields request raised:", exc)

        # variants
        variants = p.get("variants") or []
        for v in variants:
            vid = str(v.get("id", ""))
            vtitle = v.get("title", "")
            val = v.get("metafields", {}).get("custom", {}).get("ecom_price", "")
            print(f"  Variant {vid} ({vtitle}) - variant.metafields.custom.ecom_price: {repr(val)}")

            # REST check for variant metafields
            try:
                resp = requests.get(f"{base}/variants/{vid}/metafields.json", headers=headers, timeout=20)
                if resp.ok:
                    body = resp.json()
                    items = body.get("metafields", []) if isinstance(body, dict) else []
                    matches = [mf for mf in items if mf.get("namespace") == "custom" and mf.get("key") == "ecom_price"]
                    print("    REST variant metafields count:", len(matches))
                    if matches:
                        for mf in matches:
                            print("      ->", json.dumps(mf, ensure_ascii=False))
                else:
                    print("    REST variant metafields request failed status:", resp.status_code)
            except Exception as exc:
                print("    REST variant metafields request raised:", exc)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
