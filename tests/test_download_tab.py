import unittest

from shopify_erp.ui.tab_download import _needs_metafield_enrichment


class TestDownloadTabHelpers(unittest.TestCase):
    def test_product_level_metafields_trigger_enrichment(self):
        self.assertTrue(_needs_metafield_enrichment(["id", "metafields.custom.ecom_price"]))

    def test_variant_level_metafields_trigger_enrichment(self):
        self.assertTrue(_needs_metafield_enrichment(["id", "variants.0.metafields.custom.ecom_price"]))

    def test_non_metafield_selection_does_not_trigger_enrichment(self):
        self.assertFalse(_needs_metafield_enrichment(["id", "title", "variants.0.sku"]))


if __name__ == "__main__":
    unittest.main()