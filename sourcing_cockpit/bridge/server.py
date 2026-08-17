from __future__ import annotations

import argparse
import json
import os
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any


LWA_TOKEN_URL = "https://api.amazon.com/auth/o2/token"
REGION_ENDPOINTS = {
    "NA": "https://sellingpartnerapi-na.amazon.com",
    "EU": "https://sellingpartnerapi-eu.amazon.com",
    "FE": "https://sellingpartnerapi-fe.amazon.com",
}


class ApiError(RuntimeError):
    def __init__(self, message: str, status: int | None = None, payload: Any = None):
        super().__init__(message)
        self.status = status
        self.payload = payload


@dataclass(frozen=True)
class Config:
    client_id: str
    client_secret: str
    refresh_token: str
    seller_id: str
    marketplace_id: str
    region: str = "NA"
    user_agent: str = "SourcingCockpit/0.1.0 (Language=Python/3.12)"

    @property
    def endpoint(self) -> str:
        try:
            return REGION_ENDPOINTS[self.region.upper()]
        except KeyError as exc:
            raise ValueError(f"Unsupported region {self.region!r}; expected NA, EU, or FE") from exc

    @classmethod
    def load(cls, path: Path) -> "Config":
        data = json.loads(path.read_text(encoding="utf-8"))
        required = ["client_id", "client_secret", "refresh_token", "seller_id", "marketplace_id"]
        missing = [key for key in required if not str(data.get(key, "")).strip()]
        if missing:
            raise ValueError(f"Missing required config keys: {', '.join(missing)}")
        return cls(
            client_id=data["client_id"],
            client_secret=data["client_secret"],
            refresh_token=data["refresh_token"],
            seller_id=data["seller_id"],
            marketplace_id=data["marketplace_id"],
            region=data.get("region", "NA"),
            user_agent=data.get("user_agent", cls.user_agent),
        )


class RateGate:
    """Simple process-local request spacing for endpoints with per-second limits."""

    def __init__(self, min_interval_seconds: float = 0.21):
        self._min_interval = min_interval_seconds
        self._next = 0.0
        self._lock = threading.Lock()

    def wait(self) -> None:
        with self._lock:
            now = time.monotonic()
            if now < self._next:
                time.sleep(self._next - now)
            self._next = time.monotonic() + self._min_interval


class SpApiClient:
    def __init__(self, config: Config):
        self.config = config
        self._token: str | None = None
        self._token_expires_at = 0.0
        self._token_lock = threading.Lock()
        self._restrictions_gate = RateGate(0.21)
        self._fees_gate = RateGate(1.02)

    def _json_request(
        self,
        url: str,
        *,
        method: str = "GET",
        headers: dict[str, str] | None = None,
        form: dict[str, str] | None = None,
        body: Any = None,
        timeout: float = 25.0,
    ) -> tuple[Any, dict[str, str]]:
        req_headers = dict(headers or {})
        data: bytes | None = None

        if form is not None:
            data = urllib.parse.urlencode(form).encode()
            req_headers["Content-Type"] = "application/x-www-form-urlencoded"
        elif body is not None:
            data = json.dumps(body).encode()
            req_headers["Content-Type"] = "application/json"

        request = urllib.request.Request(url, data=data, headers=req_headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                raw = response.read()
                payload = json.loads(raw.decode("utf-8")) if raw else {}
                return payload, dict(response.headers.items())
        except urllib.error.HTTPError as exc:
            raw = exc.read()
            try:
                payload = json.loads(raw.decode("utf-8")) if raw else {}
            except Exception:
                payload = raw.decode("utf-8", errors="replace")
            message = _amazon_error_message(payload) or f"HTTP {exc.code}"
            raise ApiError(message, exc.code, payload) from exc
        except urllib.error.URLError as exc:
            raise ApiError(f"Network error: {exc.reason}") from exc

    def access_token(self) -> str:
        with self._token_lock:
            if self._token and time.time() < self._token_expires_at - 60:
                return self._token

            payload, _ = self._json_request(
                LWA_TOKEN_URL,
                method="POST",
                form={
                    "grant_type": "refresh_token",
                    "refresh_token": self.config.refresh_token,
                    "client_id": self.config.client_id,
                    "client_secret": self.config.client_secret,
                },
            )
            token = payload.get("access_token")
            if not token:
                raise ApiError("LWA response did not contain access_token", payload=payload)
            expires_in = int(payload.get("expires_in", 3600))
            self._token = token
            self._token_expires_at = time.time() + expires_in
            return token

    def _headers(self) -> dict[str, str]:
        return {
            "x-amz-access-token": self.access_token(),
            "x-amz-date": time.strftime("%Y%m%dT%H%M%SZ", time.gmtime()),
            "user-agent": self.config.user_agent,
            "accept": "application/json",
        }

    def get_restrictions(
        self,
        asin: str,
        marketplace_ids: list[str] | None = None,
        condition_type: str | None = None,
    ) -> dict[str, Any]:
        self._restrictions_gate.wait()
        params: list[tuple[str, str]] = [
            ("asin", asin),
            ("sellerId", self.config.seller_id),
            ("marketplaceIds", ",".join(marketplace_ids or [self.config.marketplace_id])),
        ]
        if condition_type:
            params.append(("conditionType", condition_type))
        url = (
            f"{self.config.endpoint}/listings/2021-08-01/restrictions?"
            + urllib.parse.urlencode(params)
        )
        payload, headers = self._json_request(url, headers=self._headers())
        result = classify_restrictions(payload)
        result["rateLimit"] = headers.get("x-amzn-RateLimit-Limit")
        result["requestId"] = headers.get("x-amzn-RequestId")
        return result

    def fee_estimate(
        self,
        *,
        asin: str,
        marketplace_id: str,
        price: float,
        shipping: float = 0.0,
        is_amazon_fulfilled: bool = False,
    ) -> dict[str, Any]:
        self._fees_gate.wait()
        url = f"{self.config.endpoint}/products/fees/v0/items/{urllib.parse.quote(asin)}/feesEstimate"
        body = {
            "FeesEstimateRequest": {
                "MarketplaceId": marketplace_id,
                "IsAmazonFulfilled": bool(is_amazon_fulfilled),
                "PriceToEstimateFees": {
                    "ListingPrice": {"CurrencyCode": "USD", "Amount": float(price)},
                    "Shipping": {"CurrencyCode": "USD", "Amount": float(shipping)},
                },
                "Identifier": f"sourcing-cockpit-{asin}-{int(time.time())}",
            }
        }
        payload, headers = self._json_request(
            url,
            method="POST",
            headers=self._headers(),
            body=body,
        )
        estimate = payload.get("payload", {}).get("FeesEstimateResult", {}).get("FeesEstimate", {})
        total = estimate.get("TotalFeesEstimate", {})
        details = estimate.get("FeeDetailList") or estimate.get("FeeDetails") or []
        return {
            "totalFees": {
                "amount": total.get("Amount"),
                "currency": total.get("CurrencyCode"),
            },
            "details": details,
            "raw": payload,
            "rateLimit": headers.get("x-amzn-RateLimit-Limit"),
            "requestId": headers.get("x-amzn-RequestId"),
        }


def _amazon_error_message(payload: Any) -> str | None:
    if isinstance(payload, dict):
        errors = payload.get("errors")
        if isinstance(errors, list) and errors:
            first = errors[0]
            if isinstance(first, dict):
                return first.get("message") or first.get("code")
        return payload.get("error_description") or payload.get("message")
    return None


def classify_restrictions(payload: dict[str, Any]) -> dict[str, Any]:
    restrictions = payload.get("restrictions") or []
    reasons: list[dict[str, Any]] = []
    for restriction in restrictions:
        reasons.extend(restriction.get("reasons") or [])

    reason_codes = sorted({
        str(reason.get("reasonCode"))
        for reason in reasons
        if reason.get("reasonCode")
    })
    messages = [str(reason.get("message")) for reason in reasons if reason.get("message")]

    approval_url = None
    for reason in reasons:
        for link in reason.get("links") or []:
            resource = link.get("resource")
            if resource and str(resource).startswith("https://"):
                approval_url = str(resource)
                if reason.get("reasonCode") == "APPROVAL_REQUIRED":
                    break
        if approval_url and reason.get("reasonCode") == "APPROVAL_REQUIRED":
            break

    if not restrictions or not reasons:
        status = "SELLABLE"
    elif "NOT_ELIGIBLE" in reason_codes:
        status = "RESTRICTED"
    elif "APPROVAL_REQUIRED" in reason_codes:
        status = "APPROVAL_REQUIRED"
    elif "ASIN_NOT_FOUND" in reason_codes:
        status = "UNKNOWN"
    else:
        status = "RESTRICTED"

    return {
        "status": status,
        "reasonCodes": reason_codes,
        "message": " | ".join(dict.fromkeys(messages)),
        "approvalUrl": approval_url,
        "restrictions": restrictions,
    }


class Handler(BaseHTTPRequestHandler):
    server_version = "SourcingCockpitBridge/0.1.0"

    @property
    def client(self) -> SpApiClient:
        return self.server.spapi_client  # type: ignore[attr-defined]

    @property
    def config(self) -> Config:
        return self.server.spapi_client.config  # type: ignore[attr-defined]

    def log_message(self, fmt: str, *args: Any) -> None:
        print(f"[bridge] {self.address_string()} - {fmt % args}")

    def _cors(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")

    def _send(self, status: int, payload: Any) -> None:
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self._cors()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _read_json(self, max_bytes: int = 1_000_000) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0") or 0)
        if length <= 0 or length > max_bytes:
            raise ValueError("Invalid request body size")
        return json.loads(self.rfile.read(length).decode("utf-8"))

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/health":
            masked = self.config.seller_id
            if len(masked) > 6:
                masked = f"{masked[:3]}…{masked[-3:]}"
            self._send(200, {
                "ok": True,
                "region": self.config.region,
                "marketplaceId": self.config.marketplace_id,
                "sellerIdMasked": masked,
                "pid": os.getpid(),
            })
            return
        self._send(404, {"ok": False, "error": "Not found"})

    def do_POST(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        try:
            body = self._read_json()
            if parsed.path == "/eligibility":
                self._eligibility(body)
            elif parsed.path == "/fees":
                self._fees(body)
            else:
                self._send(404, {"ok": False, "error": "Not found"})
        except ValueError as exc:
            self._send(400, {"ok": False, "error": str(exc)})
        except ApiError as exc:
            self._send(exc.status or 502, {
                "ok": False,
                "error": str(exc),
                "amazonStatus": exc.status,
                "details": exc.payload,
            })
        except Exception as exc:
            self._send(500, {"ok": False, "error": f"{type(exc).__name__}: {exc}"})

    def _eligibility(self, body: dict[str, Any]) -> None:
        raw_asins = body.get("asins")
        if not isinstance(raw_asins, list) or not raw_asins:
            raise ValueError("asins must be a non-empty array")
        asins = []
        for value in raw_asins[:100]:
            asin = str(value).strip().upper()
            if not (len(asin) == 10 and asin.isalnum()):
                raise ValueError(f"Invalid ASIN: {value!r}")
            asins.append(asin)

        marketplace_ids = body.get("marketplaceIds")
        if marketplace_ids is None:
            marketplace_ids = [self.config.marketplace_id]
        if not isinstance(marketplace_ids, list) or not all(isinstance(x, str) and x for x in marketplace_ids):
            raise ValueError("marketplaceIds must be an array of strings")

        condition = body.get("conditionType") or None
        results: dict[str, Any] = {}

        # Concurrency keeps browser batches responsive; RateGate still caps request pacing.
        with ThreadPoolExecutor(max_workers=min(4, len(asins))) as pool:
            futures = {
                pool.submit(self.client.get_restrictions, asin, marketplace_ids, condition): asin
                for asin in asins
            }
            for future in as_completed(futures):
                asin = futures[future]
                try:
                    results[asin] = future.result()
                except Exception as exc:
                    results[asin] = {
                        "status": "UNKNOWN",
                        "reasonCodes": [],
                        "message": str(exc),
                        "approvalUrl": None,
                        "error": True,
                    }

        self._send(200, {"ok": True, "results": results})

    def _fees(self, body: dict[str, Any]) -> None:
        asin = str(body.get("asin", "")).strip().upper()
        if not (len(asin) == 10 and asin.isalnum()):
            raise ValueError("Invalid asin")
        marketplace_id = str(body.get("marketplaceId") or self.config.marketplace_id)
        price = float(body.get("price"))
        shipping = float(body.get("shipping") or 0)
        if price <= 0 or shipping < 0:
            raise ValueError("price must be > 0 and shipping must be >= 0")
        result = self.client.fee_estimate(
            asin=asin,
            marketplace_id=marketplace_id,
            price=price,
            shipping=shipping,
            is_amazon_fulfilled=bool(body.get("isAmazonFulfilled")),
        )
        self._send(200, {"ok": True, "result": result})


def main() -> int:
    parser = argparse.ArgumentParser(description="Local SP-API bridge for Sourcing Cockpit")
    parser.add_argument("--config", type=Path, default=Path(__file__).with_name("config.json"))
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()

    config = Config.load(args.config)
    client = SpApiClient(config)
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    server.spapi_client = client  # type: ignore[attr-defined]

    print(f"Sourcing Cockpit bridge listening on http://127.0.0.1:{args.port}")
    print(f"Region={config.region} marketplace={config.marketplace_id} seller={config.seller_id[:3]}…")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
