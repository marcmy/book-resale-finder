import unittest

from server import classify_restrictions, endpoint_for_marketplaces


class ClassifyRestrictionsTests(unittest.TestCase):
    def test_empty_is_sellable(self):
        self.assertEqual(classify_restrictions({"restrictions": []})["status"], "SELLABLE")

    def test_nonempty_without_reasons_is_not_sellable(self):
        result = classify_restrictions({"restrictions": [{}]})
        self.assertEqual(result["status"], "RESTRICTED")

    def test_approval_required(self):
        result = classify_restrictions({
            "restrictions": [{
                "reasons": [{
                    "reasonCode": "APPROVAL_REQUIRED",
                    "message": "Approval required",
                    "links": [{"resource": "https://sellercentral.amazon.com/approval"}],
                }]
            }]
        })
        self.assertEqual(result["status"], "APPROVAL_REQUIRED")
        self.assertEqual(result["approvalUrl"], "https://sellercentral.amazon.com/approval")

    def test_not_eligible_wins(self):
        result = classify_restrictions({
            "restrictions": [{
                "reasons": [
                    {"reasonCode": "APPROVAL_REQUIRED"},
                    {"reasonCode": "NOT_ELIGIBLE"},
                ]
            }]
        })
        self.assertEqual(result["status"], "RESTRICTED")

    def test_asin_not_found_is_unknown(self):
        result = classify_restrictions({
            "restrictions": [{"reasons": [{"reasonCode": "ASIN_NOT_FOUND"}]}]
        })
        self.assertEqual(result["status"], "UNKNOWN")


class MarketplaceRoutingTests(unittest.TestCase):
    def test_us_and_canada_use_na_endpoint(self):
        us = endpoint_for_marketplaces(["ATVPDKIKX0DER"])
        ca = endpoint_for_marketplaces(["A2EUQ1WTGCTBG2"])
        self.assertEqual(us, "https://sellingpartnerapi-na.amazon.com")
        self.assertEqual(ca, us)

    def test_uk_uses_eu_endpoint(self):
        self.assertEqual(
            endpoint_for_marketplaces(["A1F83G8C2ARO7P"]),
            "https://sellingpartnerapi-eu.amazon.com",
        )

    def test_cross_region_batch_is_rejected(self):
        with self.assertRaises(ValueError):
            endpoint_for_marketplaces(["ATVPDKIKX0DER", "A1F83G8C2ARO7P"])


if __name__ == "__main__":
    unittest.main()
