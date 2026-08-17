from __future__ import annotations

import argparse
import json
import math
import os
import secrets
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
MARKETPLACE_INFO = {
    "ATVPDKIKX0DER": {"region": "NA", "currency": "USD"},  # US
    "A2EUQ1WTGCTBG2": {"region": "NA", "currency": "CAD"},  # Canada
    "A1F83G8C2ARO7P": {"region": "EU", "currency": "GBP"},  # United Kingdom
}
EXTENSION_ORIGIN_PREFIXES = (
    "chrome-extension://",
    "moz-extension://",
    "edge-extension://",
)
PAIR_PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Sourcing Cockpit pairing</title>
<style>
body{font-family:system-ui,-apple-system,"Segoe UI",sans-serif;max-width:620px;margin:12vh auto;padding:0 24px;color:#202124}
.card{border:1px solid #d9dce1;border-radius:12px;padding:24px;box-shadow:0 4px 18px rgba(0,0,0,.08)}
h1{font-size:22px;margin-top:0}p{line-height:1.5}.muted{color:#666}
</style>
</head>
<body>
<div class="card" id="sc-pair-card">
<h1>Sourcing Cockpit</h1>
<p id="sc-pair-status">Waiting for the Sourcing Cockpit browser extension to complete pairing…</p>
<p class="muted">If this message does not change, make sure the signed extension is installed and then use <b>Pair browser</b> from the Sourcing Cockpit tray app.</p>
</div>
</body>
</html>"""


def endpoint_for_marketplaces(marketplace_ids: list[str]) -> str:
    if not marketplace_ids:
        raise ValueError("At least one marketplace ID is required")

    regions: set[str] = set()
    for marketplace_id in marketplace_ids:
        info = MARKETPLACE_INFO.get(marketplace_id)
        if not info:
            raise ValueError(f"Unsupported marketplace: {marketplace_id}")
        regions.add(str(info["region"]))

    if len(regions) != 1:
        raise ValueError("A single SP-API request cannot mix marketplaces from different regions")
    return REGION_ENDPOINTS[regions.pop()]


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
    user_agent: str = "SourcingCockpit/0.2.1 (Language=Python/3.12)"

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
            client_id=str(data["client_id"]).strip(),
            client_secret=str(data["client_secret"]).strip(),
            refresh_token=str(data["refresh_token"]).strip(),
            seller_id=str(data["seller_id"]).strip(),
            marketplace_id=str(data["marketplace_id"]).strip(),
            region=str(data.get("region", "NA")).strip().upper() or "NA",
            user_agent=str(data.get("user_agent") or cls.user_agent),
        )


class RateGate:
    """Process-local request spacing for endpoints with per-second limits."""

    def __init__(self, min_interval_seconds: float):
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
        # Amazon's documented defaults are 5 rps for Listings Restrictions and
        # 1 rps for getMyFeesEstimateForASIN. Stay slightly below each limit.
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
            data = urllib.parse.urlencode(form).encode("utf-8")
            req_headers["Content-Type"] = "application/x-www-form-urlencoded"
        elif body is not None:
            data = json.dumps(body, allow_nan=False).encode("utf-8")
            req_headers["Content-Type"] = "application/json"

        request = urllib.request.Request(url, data=data, headers=req_headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                raw = response.read()
                if not raw:
                    payload: Any = {}
                else:
                    try:
                        payload = json.loads(raw.decode("utf-8"))
                    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                        raise ApiError("Amazon returned an invalid JSON response") from exc
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
            token = payload.get("access_token") if isinstance(payload, dict) else None
            if not token:
                raise ApiError("LWA response did not contain access_token", payload=payload)
            expires_in = int(payload.get("expires_in", 3600))
            self._token = str(token)
            self._token_expires_at = time.time() + expires_in
            return self._token

    def _headers(self) -> dict[str, str]:
        return {
            "x-amz-access-token": self.access_token(),
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
        marketplaces = marketplace_ids or [self.config.marketplace_id]
        endpoint = endpoint_for_marketplaces(marketplaces)
        params: list[tuple[str, str]] = [
            ("asin", asin),
            ("sellerId", self.config.seller_id),
            ("marketplaceIds", ",".join(marketplaces)),
        ]
        if condition_type:
            params.append(("conditionType", condition_type))
        url = f"{endpoint}/listings/2021-08-01/restrictions?{urllib.parse.urlencode(params)}"
        payload, headers = self._json_request(url, headers=self._headers())
        if not isinstance(payload, dict):
            raise ApiError("Amazon returned an unexpected restrictions response")
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
        info = MARKETPLACE_INFO.get(marketplace_id)
        if not info:
            raise ValueError(f"Fee estimates are not configured for marketplace {marketplace_id}")
        currency = str(info["currency"])
        endpoint = endpoint_for_marketplaces([marketplace_id])

        url = f"{endpoint}/products/fees/v0/items/{urllib.parse.quote(asin)}/feesEstimate"
        body = {
            "FeesEstimateRequest": {
                "MarketplaceId": marketplace_id,
                "IsAmazonFulfilled": bool(is_amazon_fulfilled),
                "PriceToEstimateFees": {
                    "ListingPrice": {"CurrencyCode": currency, "Amount": float(price)},
                    "Shipping": {"CurrencyCode": currency, "Amount": float(shipping)},
                },
                "Identifier": f"sourcing-cockpit-{asin}-{time.time_ns()}",
            }
        }
        payload, headers = self._json_request(url, method="POST", headers=self._headers(), body=body)
        if not isinstance(payload, dict):
            raise ApiError("Amazon returned an unexpected fee response")
        estimate = payload.get("payload", {}).get("FeesEstimateResult", {}).get("FeesEstimate", {})
        total = estimate.get("TotalFeesEstimate", {})
        details = estimate.get("FeeDetailList") or estimate.get("FeeDetails") or []
        return {
            "totalFees": {
                "amount": total.get("Amount"),
                "currency": total.get("CurrencyCode") or currency,
            },
            "details": details,
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
        if isinstance(restriction, dict):
            reasons.extend(x for x in (restriction.get("reasons") or []) if isinstance(x, dict))

    reason_codes = sorted(
        {
            str(reason.get("reasonCode"))
            for reason in reasons
            if reason.get("reasonCode")
        }
    )
    messages = [str(reason.get("message")) for reason in reasons if reason.get("message")]

    approval_url = None
    for reason in reasons:
        for link in reason.get("links") or []:
            if not isinstance(link, dict):
                continue
            resource = link.get("resource")
            if resource and str(resource).startswith("https://"):
                approval_url = str(resource)
                if reason.get("reasonCode") == "APPROVAL_REQUIRED":
                    break
        if approval_url and reason.get("reasonCode") == "APPROVAL_REQUIRED":
            break

    # An empty restrictions array is the only positive indication that there is
    # no listing restriction. A malformed/non-empty restriction without reasons
    # must never be painted green.
    if not restrictions:
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
    server_version = "SourcingCockpitBridge/0.2.1"
    sys_version = ""

    @property
    def client(self) -> SpApiClient:
        return self.server.spapi_client  # type: ignore[attr-defined]

    @property
    def config(self) -> Config:
        return self.server.spapi_client.config  # type: ignore[attr-defined]

    def log_message(self, fmt: str, *args: Any) -> None:
        print(f"[bridge] {self.client_address[0]} - {fmt % args}")

    def _origin_allowed(self) -> bool:
        origin = (self.headers.get("Origin") or "").strip().lower()
        if not origin:
            return True
        return origin.startswith(EXTENSION_ORIGIN_PREFIXES)

    def _token_allowed(self) -> bool:
        expected = str(getattr(self.server, "bridge_token", "") or "")
        if not expected:
            # Direct developer mode may run without helper-managed pairing.
            return True
        provided = (self.headers.get("X-Sourcing-Cockpit-Token") or "").strip()
        return bool(provided) and secrets.compare_digest(provided, expected)

    def _send(self, status: int, payload: Any) -> None:
        raw = json.dumps(payload, ensure_ascii=False, allow_nan=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _send_html(self, status: int, html: str) -> None:
        raw = html.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", "default-src 'none'; style-src 'unsafe-inline'")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _read_json(self, max_bytes: int = 1_000_000) -> dict[str, Any]:
        content_type = (self.headers.get("Content-Type") or "").split(";", 1)[0].strip().lower()
        if content_type != "application/json":
            raise ValueError("Content-Type must be application/json")
        try:
            length = int(self.headers.get("Content-Length", "0") or 0)
        except ValueError as exc:
            raise ValueError("Invalid Content-Length") from exc
        if length <= 0 or length > max_bytes:
            raise ValueError("Invalid request body size")
        payload = json.loads(self.rfile.read(length).decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("JSON body must be an object")
        return payload

    def do_OPTIONS(self) -> None:
        # Extension background pages have host permissions and do not need CORS.
        # Refuse browser preflights so arbitrary websites cannot spend the user's
        # Amazon API quota through this localhost service.
        self._send(403, {"ok": False, "error": "Cross-origin web access is not allowed"})

    def do_GET(self) -> None:
        if not self._origin_allowed():
            self._send(403, {"ok": False, "error": "Origin not allowed"})
            return

        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/pair":
            self._send_html(200, PAIR_PAGE)
            return
        if parsed.path == "/health":
            masked = self.config.seller_id
            if len(masked) > 6:
                masked = f"{masked[:3]}…{masked[-3:]}"
            self._send(
                200,
                {
                    "ok": True,
                    "service": "SourcingCockpitBridge",
                    "version": "0.2.1",
                    "region": self.config.region,
                    "marketplaceId": self.config.marketplace_id,
                    "sellerIdMasked": masked,
                    "pairingRequired": bool(getattr(self.server, "bridge_token", "")),
                    "pid": os.getpid(),
                },
            )
            return
        self._send(404, {"ok": False, "error": "Not found"})

    def do_POST(self) -> None:
        if not self._origin_allowed():
            self._send(403, {"ok": False, "error": "Origin not allowed"})
            return

        parsed = urllib.parse.urlparse(self.path)
        try:
            body = self._read_json()
            if parsed.path == "/pair":
                self._pair(body)
                return
            if not self._token_allowed():
                self._send(401, {"ok": False, "error": "Browser extension is not paired with this helper"})
                return
            if parsed.path == "/eligibility":
                self._eligibility(body)
            elif parsed.path == "/fees":
                self._fees(body)
            else:
                self._send(404, {"ok": False, "error": "Not found"})
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            self._send(400, {"ok": False, "error": str(exc)})
        except ApiError as exc:
            self._send(
                exc.status or 502,
                {
                    "ok": False,
                    "error": str(exc),
                    "amazonStatus": exc.status,
                },
            )
        except Exception as exc:
            self._send(500, {"ok": False, "error": f"{type(exc).__name__}: {exc}"})

    def _pair(self, body: dict[str, Any]) -> None:
        code = str(body.get("code") or "").strip()
        expected = str(getattr(self.server, "pairing_code", "") or "")
        expires_at = float(getattr(self.server, "pairing_expires_at", 0.0) or 0.0)
        if not code or not expected or time.time() > expires_at:
            raise ValueError("Pairing window expired. Start pairing again from the Sourcing Cockpit tray app.")
        if not secrets.compare_digest(code, expected):
            raise ValueError("Invalid pairing code")

        token = str(getattr(self.server, "bridge_token", "") or "")
        if not token:
            raise ValueError("Helper bridge token is unavailable")
        self.server.pairing_code = None  # type: ignore[attr-defined]
        self.server.pairing_expires_at = 0.0  # type: ignore[attr-defined]
        callback = getattr(self.server, "pairing_callback", None)
        if callable(callback):
            try:
                callback()
            except Exception:
                pass
        self._send(200, {"ok": True, "token": token})

    def _eligibility(self, body: dict[str, Any]) -> None:
        raw_asins = body.get("asins")
        if not isinstance(raw_asins, list) or not raw_asins:
            raise ValueError("asins must be a non-empty array")

        asins: list[str] = []
        seen: set[str] = set()
        for value in raw_asins[:100]:
            asin = str(value).strip().upper()
            if not (len(asin) == 10 and asin.isalnum()):
                raise ValueError(f"Invalid ASIN: {value!r}")
            if asin not in seen:
                seen.add(asin)
                asins.append(asin)

        marketplace_ids = body.get("marketplaceIds")
        if marketplace_ids is None:
            marketplace_ids = [self.config.marketplace_id]
        if (
            not isinstance(marketplace_ids, list)
            or not marketplace_ids
            or len(marketplace_ids) > 10
            or not all(isinstance(x, str) and x in MARKETPLACE_INFO for x in marketplace_ids)
        ):
            raise ValueError("marketplaceIds must contain supported marketplace IDs")
        endpoint_for_marketplaces(marketplace_ids)

        condition = body.get("conditionType") or None
        if condition is not None and (not isinstance(condition, str) or len(condition) > 64):
            raise ValueError("Invalid conditionType")

        results: dict[str, Any] = {}
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

        marketplace_id = str(body.get("marketplaceId") or self.config.marketplace_id).strip()
        if marketplace_id not in MARKETPLACE_INFO:
            raise ValueError("Unsupported marketplace for fee estimate")

        price = float(body.get("price"))
        shipping = float(body.get("shipping") or 0)
        if not math.isfinite(price) or not math.isfinite(shipping):
            raise ValueError("price and shipping must be finite numbers")
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
    # Direct bridge development stays backwards-compatible. The packaged helper
    # sets bridge_token and a time-limited pairing code at runtime.
    server.bridge_token = os.environ.get("SOURCING_COCKPIT_BRIDGE_TOKEN", "")  # type: ignore[attr-defined]
    server.pairing_code = os.environ.get("SOURCING_COCKPIT_PAIRING_CODE") or None  # type: ignore[attr-defined]
    server.pairing_expires_at = time.time() + 300 if server.pairing_code else 0.0  # type: ignore[attr-defined]
    server.pairing_callback = None  # type: ignore[attr-defined]

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