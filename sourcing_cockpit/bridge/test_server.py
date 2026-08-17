import json
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from types import SimpleNamespace

from server import Handler, classify_restrictions, endpoint_for_marketplaces


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


class _FakeClient:
    def __init__(self):
        self.config = SimpleNamespace(
            seller_id="A1SELLER123456",
            region="NA",
            marketplace_id="ATVPDKIKX0DER",
        )

    def get_restrictions(self, asin, marketplace_ids, condition):
        return {
            "status": "SELLABLE",
            "reasonCodes": [],
            "message": "",
            "approvalUrl": None,
            "restrictions": [],
        }


class BridgePairingTests(unittest.TestCase):
    def setUp(self):
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.spapi_client = _FakeClient()
        self.server.bridge_token = "unit-test-token"
        self.server.pairing_code = "unit-test-code"
        self.server.pairing_expires_at = 9_999_999_999.0
        self.server.pairing_callback = None
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    def _post(self, path, body, token=None):
        headers = {"Content-Type": "application/json"}
        if token:
            headers["X-Sourcing-Cockpit-Token"] = token
        request = urllib.request.Request(
            self.base + path,
            data=json.dumps(body).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=2) as response:
            return response.status, json.loads(response.read().decode("utf-8"))

    def test_sensitive_endpoint_requires_pairing_token(self):
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self._post("/eligibility", {"asins": ["0123456789"]})
        self.assertEqual(ctx.exception.code, 401)

    def test_pairing_returns_token_once(self):
        status, payload = self._post("/pair", {"code": "unit-test-code"})
        self.assertEqual(status, 200)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["token"], "unit-test-token")
        self.assertIsNone(self.server.pairing_code)

    def test_paired_request_succeeds(self):
        status, payload = self._post(
            "/eligibility",
            {"asins": ["0123456789"], "marketplaceIds": ["ATVPDKIKX0DER"]},
            token="unit-test-token",
        )
        self.assertEqual(status, 200)
        self.assertEqual(payload["results"]["0123456789"]["status"], "SELLABLE")


if __name__ == "__main__":
    unittest.main()
