from __future__ import annotations

import asyncio
import re
from typing import Any

from .constants import RATE_LIMIT_URL
from .ebay import EbayClient as _BaseEbayClient
from .models import QuotaInfo


class EbayClient(_BaseEbayClient):
    """Quota-reporting compatibility and diagnostics for eBay Analytics."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.quota_diagnostics: list[str] = []

    @staticmethod
    def _normalized_method_name(raw_name: object) -> str:
        text = str(raw_name or "").strip()
        text = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", text)
        return re.sub(r"[^a-z0-9]+", "_", text.casefold()).strip("_")

    @classmethod
    def _quotas_from_payload(cls, payload: dict[str, Any]) -> tuple[QuotaInfo, QuotaInfo]:
        search_resource: dict[str, Any] | None = None
        item_resource: dict[str, Any] | None = None
        search_name = "search"
        item_name = "getItem"
        search_score = item_score = -1

        search_priorities = {
            "search": 100,
            "item_summary_search": 90,
            "itemsummary_search": 90,
            "item_summary": 80,
        }
        item_priorities = {
            "get_item": 100,
            "getitem": 100,
            "item": 80,
        }

        for group in payload.get("rateLimits") or []:
            api_name = str(group.get("apiName") or "").casefold()
            api_context = str(group.get("apiContext") or "").casefold()
            if api_name and api_name != "browse":
                continue
            if api_context and api_context != "buy":
                continue

            for resource in group.get("resources") or []:
                raw_name = str(resource.get("name") or "")
                normalized = cls._normalized_method_name(raw_name)

                candidate_search_score = search_priorities.get(normalized, -1)
                if (
                    candidate_search_score < 0
                    and normalized.startswith("search")
                    and "image" not in normalized
                ):
                    candidate_search_score = 70
                if candidate_search_score > search_score:
                    search_resource = resource
                    search_name = raw_name or "search"
                    search_score = candidate_search_score

                candidate_item_score = item_priorities.get(normalized, -1)
                if candidate_item_score > item_score:
                    item_resource = resource
                    item_name = raw_name or "getItem"
                    item_score = candidate_item_score

        search = (
            cls._quota_for_resource(search_resource, search_name)
            if search_resource is not None and search_score >= 0
            else QuotaInfo(resource="search")
        )
        item = (
            cls._quota_for_resource(item_resource, item_name)
            if item_resource is not None and item_score >= 0
            else QuotaInfo(resource="getItem")
        )
        return search, item

    @classmethod
    def _quota_from_payload(cls, payload: dict[str, Any]) -> QuotaInfo:
        return cls._quotas_from_payload(payload)[0]

    def _sanitize_diagnostic(self, text: object) -> str:
        cleaned = " ".join(str(text or "").split())
        for secret in (self.client_id, self.client_secret, self.token):
            if secret:
                cleaned = cleaned.replace(str(secret), "[redacted]")
        cleaned = re.sub(r"(?i)\b(?:bearer|basic)\s+[A-Za-z0-9._~+/=-]+", "[redacted authorization]", cleaned)
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
        search, item = self._quotas_from_payload(filtered_payload)
        if search.remaining is not None and item.remaining is not None:
            return search, item
        if filtered_payload:
            self._record_quota_diagnostic(
                "Quota diagnostic (filtered response): no usable Browse search/item quota was found. "
                f"Returned entries: {self._payload_inventory(filtered_payload)}"
            )

        full_payload = await self._request_quota_payload(label="unfiltered", params=None)
        full_search, full_item = self._quotas_from_payload(full_payload)
        if search.remaining is None and full_search.remaining is not None:
            search = full_search
        if item.remaining is None and full_item.remaining is not None:
            item = full_item
        if full_payload and (search.remaining is None or item.remaining is None):
            self._record_quota_diagnostic(
                "Quota diagnostic (unfiltered response): one or more Browse quotas were still missing. "
                f"Returned entries: {self._payload_inventory(full_payload)}"
            )
        return search, item


__all__ = ["EbayClient"]
