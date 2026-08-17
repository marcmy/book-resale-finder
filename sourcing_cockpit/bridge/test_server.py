import unittest

from server import classify_restrictions


class ClassifyRestrictionsTests(unittest.TestCase):
    def test_empty_is_sellable(self):
        self.assertEqual(classify_restrictions({"restrictions": []})["status"], "SELLABLE")

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


if __name__ == "__main__":
    unittest.main()
