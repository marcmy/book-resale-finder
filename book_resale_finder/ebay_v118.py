from __future__ import annotations

import asyncio
import re
from typing import Any

from .constants import RATE_LIMIT_URL
from .ebay import EbayClient as _BaseEbayClient
from .ebay import EbayQuotaSafetyError
from .models import QuotaInfo


class SharedBrowseQuotaSafetyError(EbayQuotaSafetyError):
    def __init__(self) -> None:
        self.category = "browse"
        RuntimeError.__init__(
            self,
            "Stopped before the reserved eBay Browse API quota would be used.",
        )


class EbayClient(_BaseEbayClient):
    """Shared Browse-quota parsing, enforcement, and diagnostics."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.quota_diagnostics: list[str] = []
        self._browse_call_budget: int | None = None

    @staticmethod
    def _normalized_method_name(raw_name: object) -> str:
        text = str(raw_name or "").strip()
        text = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", text)
        return re.sub(r"[^a-z0-9]+", "_", text.casefold()).strip("_")

    @classmethod
    def _quotas_from_payload(cls, payload: dict[str, Any]) -> tuple[QuotaInfo, QuotaInfo]:
        """Return the shared Browse quota and the unused bulk-getItems quota.

        Production Analytics responses identify the normal Browse pool as
        ``buy.browse``. All Browse methods used by this application—search and
        getItem—consume that same pool. ``buy.browse.item.bulk`` is the
        separate getItems quota and is intentionally not used for safety.
        """
        browse_resource: dict[str, Any] | None = None
        bulk_resource: dict[str, Any] | None = None
        browse_name = "buy.browse"
        bulk_name = "buy.browse.item.bulk"
        browse_score = bulk_score = -1

        browse_priorities = {
            "buy_browse": 200,
            "browse": 190,
            # Compatibility with older/documentation-style payloads.
            "search": 100,
            "item_summary_search": 90,
            "itemsummary_search": 90,
            "item_summary": 80,
        }
        bulk_priorities = {
            "buy_browse_item_bulk": 200,
            "browse_item_bulk": 190,
            "get_items": 100,
            "getitems": 100,
        }

        for group in payload.get("rateLimits") or []:
            api_name = str(group.get("apiName") or "").casefold()
            api_context = str(group.get("apiContext") or "").casefold()
            if api_name and api_name != "browse":
                continue
            if api_context and api_context != "buy":
                continue

            for resource in group.get("resources") or []:
                if not isinstance(resource, dict):
                    continue
                raw_name = str(resource.get("name") or "")
                normalized = cls._normalized_method_name(raw_name)

                candidate_bulk_score = bulk_priorities.get(normalized, -1)
                if candidate_bulk_score > bulk_score:
                    bulk_resource = resource
                    bulk_name = raw_name or bulk_name
                    bulk_score = candidate_bulk_score

                candidate_browse_score = browse_priorities.get(normalized, -1)
                if (
                    candidate_browse_score < 0
                    and normalized.startswith("search")
                    and "image" not in normalized
                ):
                    candidate_browse_score = 70
                if "bulk" in normalized:
                    candidate_browse_score = -1
                if candidate_browse_score > browse_score:
                    browse_resource = resource
                    browse_name = raw_name or browse_name
                    browse_score = candidate_browse_score

        browse = (
            cls._quota_for_resource(browse_resource, browse_name)
            if browse_resource is not None and browse_score >= 0
            else QuotaInfo(resource="buy.browse")
        )
        bulk = (
            cls._quota_for_resource(bulk_resource, bulk_name)
            if bulk_resource is not None and bulk_score >= 0
            else QuotaInfo(resource="buy.browse.item.bulk")
        )
        return browse, bulk

    @classmethod
    def _quota_from_payload(cls, payload: dict[str, Any]) -> QuotaInfo:
        return cls._quotas_from_payload(payload)[0]

    def configure_quota_safety(
        self,
        search_quota: QuotaInfo,
        item_quota: QuotaInfo,
        reserve: int,
    ) -> None:
        del item_quota
        reserve = max(0, int(reserve))
        self._browse_call_budget = (
            max(0, search_quota.remaining - reserve)
            if search_quota.remaining is not None
            else None
        )

    async def _claim_api_call(self, call_kind: str) -> None:
        # Search and getItem calls consume the same buy.browse daily pool.
        async with self._call_lock:
            if self._browse_call_budget is not None and self.api_calls >= self._browse_call_budget:
                raise SharedBrowseQuotaSafetyError()
            self.api_calls += 1
            self.api_call_breakdown[call_kind] += 1
            if self.on_api_call:
                self.on_api_call(self.api_calls)

    def _sanitize_diagnostic(self, text: object) -> str:
        cleaned = " ".join(str(text or "").split())
        for secret in (self.client_id, self.client_secret, self.token):
            if secret:
                cleaned = cleaned.replace(str(secret), "[redacted]")
        cleaned = re.sub(
            r"(?i)\b(?:bearer|basic)\s+[A-Za-z0-9._~+/=-]+",
            "[redacted authorization]",
            cleaned,
        )
        return cleaned[:600] or "No additional detail was returned."

    def _record_quota_diagnostic(self, message: str) -> None:
        sanitized = self._sanitize_diagnostic(message)
        if sanitized not in self.quota_diagnostics:
            self.quota_diagnostics.append(sanitized)

    @staticmethod
    def _payload_inventory(payload: dict[str, Any]) -> str:
        groups: list[str] = []
        for group in payload.get("rateLimits") or []:
            api_name = str(group.get("apiName") or "unnamed")
            api_context = str(group.get("apiContext") or "no-context")
            resources = [
                str(resource.get("name") or "unnamed")
                for resource in (group.get("resources") or [])
                if isinstance(resource, dict)
            ]
            resource_text = ", ".join(resources[:12]) or "no resources"
            if len(resources) > 12:
                resource_text += f", +{len(resources) - 12} more"
            groups.append(f"{api_context}/{api_name}: {resource_text}")
        return "; ".join(groups[:8]) or "no rateLimits groups"

    async def _request_quota_payload(
        self,
        *,
        label: str,
        params: dict[str, str] | None,
    ) -> dict[str, Any]:
        """Call Analytics directly so status, empty-body, and JSON failures remain visible."""
        backoff = 1.0
        for attempt in range(self.max_retries + 1):
            try:
                await self.rate_limiter.acquire()
                response = await self.http.request(
                    "GET",
                    RATE_LIMIT_URL,
                    headers={
                        "Authorization": f"Bearer {self.token}",
                        "Accept": "application/json",
                    },
                    params=params,
                )
            except Exception as exc:
                self._record_quota_diagnostic(
                    f"Quota diagnostic ({label} request): network/client error: {exc}"
                )
                return {}

            if response.status_code == 401 and attempt == 0:
                try:
                    self.token = await self._fetch_token()
                except Exception as exc:
                    self._record_quota_diagnostic(
                        f"Quota diagnostic ({label} request): token refresh failed: {exc}"
                    )
                    return {}
                continue

            if response.status_code == 429 or response.status_code >= 500:
                if attempt < self.max_retries:
                    retry_after = response.headers.get("Retry-After")
                    try:
                        delay = float(retry_after) if retry_after else backoff
                    except ValueError:
                        delay = backoff
                    await asyncio.sleep(min(max(delay, 0.5), 30.0))
                    backoff = min(backoff * 2, 30.0)
                    continue

            if response.status_code == 204:
                self._record_quota_diagnostic(
                    f"Quota diagnostic ({label} request): HTTP 204 No Content."
                )
                return {}
            if response.status_code >= 400:
                self._record_quota_diagnostic(
                    f"Quota diagnostic ({label} request): HTTP {response.status_code}: "
                    f"{self._error_detail(response)}"
                )
                return {}
            if not response.content or not response.text.strip():
                self._record_quota_diagnostic(
                    f"Quota diagnostic ({label} request): HTTP {response.status_code} with an empty response body."
                )
                return {}

            try:
                payload = response.json()
            except ValueError:
                self._record_quota_diagnostic(
                    f"Quota diagnostic ({label} request): HTTP {response.status_code} returned invalid JSON."
                )
                return {}
            if not isinstance(payload, dict):
                self._record_quota_diagnostic(
                    f"Quota diagnostic ({label} request): HTTP {response.status_code} returned "
                    f"{type(payload).__name__}, not a JSON object."
                )
                return {}
            return payload

        self._record_quota_diagnostic(
            f"Quota diagnostic ({label} request): request ended without a usable response."
        )
        return {}

    async def fetch_quotas(self) -> tuple[QuotaInfo, QuotaInfo]:
        filtered_payload = await self._request_quota_payload(
            label="filtered",
            params={"api_name": "browse", "api_context": "buy"},
        )
        browse, bulk = self._quotas_from_payload(filtered_payload)
        if browse.remaining is not None:
            return browse, bulk
        if filtered_payload:
            self._record_quota_diagnostic(
                "Quota diagnostic (filtered response): no usable shared Browse quota was found. "
                f"Returned entries: {self._payload_inventory(filtered_payload)}"
            )

        full_payload = await self._request_quota_payload(label="unfiltered", params=None)
        full_browse, full_bulk = self._quotas_from_payload(full_payload)
        if browse.remaining is None and full_browse.remaining is not None:
            browse = full_browse
        if bulk.remaining is None and full_bulk.remaining is not None:
            bulk = full_bulk
        if full_payload and browse.remaining is None:
            self._record_quota_diagnostic(
                "Quota diagnostic (unfiltered response): the shared Browse quota was still missing. "
                f"Returned entries: {self._payload_inventory(full_payload)}"
            )
        return browse, bulk


__all__ = ["EbayClient", "SharedBrowseQuotaSafetyError"]
