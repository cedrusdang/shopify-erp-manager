import unittest
from unittest.mock import MagicMock, patch

import requests

from shopify_erp import api


class TestApiRestHelpers(unittest.TestCase):
    def test_to_gid_and_gid_tail(self):
        self.assertEqual(api._to_gid("Product", "123"), "gid://shopify/Product/123")
        self.assertEqual(api._to_gid("Product", "gid://shopify/Product/999"), "gid://shopify/Product/999")
        self.assertEqual(api._gid_tail("gid://shopify/Product/456"), "456")
        self.assertEqual(api._gid_tail("789"), "789")

    def test_rest_product_to_internal_mapping(self):
        product = {
            "id": "1001",
            "title": "Test Product",
            "body_html": "<p>Hello</p>",
            "vendor": "ACME",
            "product_type": "Shoes",
            "tags": "new, sale",
            "status": "active",
            "handle": "test-product",
            "created_at": "2026-01-01T00:00:00Z",
            "updated_at": "2026-01-02T00:00:00Z",
            "published_at": "2026-01-03T00:00:00Z",
            "template_suffix": "custom",
            "variants": [
                {
                    "id": "2001",
                    "sku": "SKU-1",
                    "title": "Default",
                    "price": "10.00",
                    "compare_at_price": "12.00",
                    "inventory_quantity": 5,
                    "barcode": "BC-1",
                    "weight": 1.2,
                    "weight_unit": "kg",
                    "taxable": True,
                    "requires_shipping": True,
                    "option1": "Red",
                    "option2": None,
                    "option3": None,
                }
            ],
            "images": [
                {
                    "src": "https://cdn.example.com/a.jpg",
                    "alt": "Front",
                }
            ],
        }

        out = api._rest_product_to_internal(product)
        self.assertEqual(out["id"], "1001")
        self.assertEqual(out["status"], "active")
        self.assertEqual(out["tags"], "new, sale")
        self.assertEqual(out["variants"][0]["id"], "2001")
        self.assertEqual(out["variants"][0]["sku"], "SKU-1")
        self.assertEqual(out["images"][0]["src"], "https://cdn.example.com/a.jpg")

    @patch("shopify_erp.api._rest_get_products_page")
    def test_fetch_products_range(self, mock_get_page):
        def make_page(product_id: int):
            return [
                {
                    "id": str(product_id),
                    "title": f"P{product_id}",
                    "body_html": "",
                    "vendor": "",
                    "product_type": "",
                    "tags": "",
                    "status": "active",
                    "handle": "",
                    "created_at": "",
                    "updated_at": "",
                    "published_at": "",
                    "template_suffix": "",
                    "variants": [],
                    "images": [],
                }
            ]

        mock_get_page.side_effect = [
            (make_page(1), "p2"),
            (make_page(2), "p3"),
            (make_page(3), None),
        ]

        products, actual_start, actual_end, has_next = api.fetch_products_range(
            "shop.myshopify.com", "token", 2, 3
        )

        self.assertEqual(actual_start, 2)
        self.assertEqual(actual_end, 3)
        self.assertFalse(has_next)
        self.assertEqual(len(products), 2)
        self.assertEqual(products[0]["id"], "2")
        self.assertEqual(products[1]["id"], "3")

    def test_fetch_products_range_invalid_input(self):
        with self.assertRaises(ValueError):
            api.fetch_products_range("s", "t", 3, 2)
        with self.assertRaises(ValueError):
            api.fetch_products_range("s", "t", 0, 2)

    @patch("shopify_erp.api._rest_get_products_page")
    def test_fetch_products_page(self, mock_get_page):
        """Test fetching a single page when it exists."""
        def make_page(product_id: int):
            return [
                {
                    "id": str(product_id),
                    "title": f"P{product_id}",
                    "body_html": "",
                    "vendor": "",
                    "product_type": "",
                    "tags": "",
                    "status": "active",
                    "handle": "",
                    "created_at": "",
                    "updated_at": "",
                    "published_at": "",
                    "template_suffix": "",
                    "variants": [],
                    "images": [],
                }
            ]

        # Scenario: Request page 2 of 3 pages total
        mock_get_page.side_effect = [
            (make_page(1), "p2"),
            (make_page(2), "p3"),
        ]

        products, actual_page, has_next = api.fetch_products_page(
            "shop.myshopify.com", "token", 2
        )

        self.assertEqual(actual_page, 2)
        self.assertTrue(has_next)
        self.assertEqual(len(products), 1)
        self.assertEqual(products[0]["id"], "2")

    @patch("shopify_erp.api._rest_get_products_page")
    def test_fetch_products_page_not_found(self, mock_get_page):
        """Test when requested page doesn't exist (fetch_products_page returns correct actual_page)."""
        def make_page(product_id: int):
            return [
                {
                    "id": str(product_id),
                    "title": f"P{product_id}",
                    "body_html": "",
                    "vendor": "",
                    "product_type": "",
                    "tags": "",
                    "status": "active",
                    "handle": "",
                    "created_at": "",
                    "updated_at": "",
                    "published_at": "",
                    "template_suffix": "",
                    "variants": [],
                    "images": [],
                }
            ]

        # Scenario: Request page 5, but only 3 pages exist
        mock_get_page.side_effect = [
            (make_page(1), "p2"),
            (make_page(2), "p3"),
            (make_page(3), None),
        ]

        products, actual_page, has_next = api.fetch_products_page(
            "shop.myshopify.com", "token", 5
        )

        self.assertEqual(actual_page, 3)  # Should return 3, the last available page
        self.assertFalse(has_next)
        self.assertEqual(len(products), 0)  # No products returned since page 5 doesn't exist

    @patch("shopify_erp.api.logger.warning")
    @patch("shopify_erp.api._log_api_table_row")
    @patch("shopify_erp.api.requests.Session")
    def test_enrich_products_with_metafields_logs_http_failures(self, mock_session_cls, mock_log_row, mock_warning):
        products = [{"id": "9364764164331", "variants": []}]

        response = MagicMock()
        response.ok = False
        response.status_code = 403
        response.text = "forbidden"

        session = MagicMock()
        session.get.return_value = response
        mock_session_cls.return_value = session

        api.enrich_products_with_metafields(
            products,
            "oz-nails-wa.myshopify.com",
            "token",
            ["metafields.custom.ecom_price"],
        )

        mock_log_row.assert_any_call(
            area="metafield-read",
            operation="product_metafield_lookup",
            method="GET",
            endpoint="https://oz-nails-wa.myshopify.com/admin/api/2024-10/products/9364764164331/metafields.json",
            product_id="9364764164331",
            variant_id="",
            field_name="metafields.custom.ecom_price",
            status_code=403,
            outcome="FAIL",
            details="HTTP 403: forbidden",
        )
        mock_warning.assert_called_once()

    @patch("shopify_erp.api.logger.exception")
    @patch("shopify_erp.api._log_api_table_row")
    @patch("shopify_erp.api.requests.Session")
    def test_enrich_products_with_metafields_logs_exceptions(self, mock_session_cls, mock_log_row, mock_exception):
        products = [{"id": "9364764164331", "variants": []}]

        session = MagicMock()
        session.get.side_effect = requests.RequestException("boom")
        mock_session_cls.return_value = session

        api.enrich_products_with_metafields(
            products,
            "oz-nails-wa.myshopify.com",
            "token",
            ["metafields.custom.ecom_price"],
        )

        mock_log_row.assert_any_call(
            area="metafield-read",
            operation="product_metafield_read_exception",
            method="GET",
            endpoint="https://oz-nails-wa.myshopify.com/admin/api/2024-10/products/9364764164331/metafields.json",
            product_id="9364764164331",
            variant_id="",
            field_name="metafields.*",
            status_code=0,
            outcome="EXCEPTION",
            details="boom",
        )
        mock_exception.assert_called_once()


if __name__ == "__main__":
    unittest.main()
