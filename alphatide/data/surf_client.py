"""Surf Data API client — the cross-chain intelligence layer.

Primary use: `wallet/labels/batch` to resolve who a Mantle-active address really
is (fund / CEX / market maker / whale) based on their history across 13 chains.

Designed for credit efficiency (see docs):
  * batches up to 100 addresses per call
  * TTL-caches results so each address is paid for at most once
  * only addresses that already passed the on-chain USD trigger are sent here

Runs in two modes:
  * **live**  — when SURF_API_KEY is set (or anonymously on the 30 cr/day free
                tier), hits https://api.asksurf.ai/gateway/v1
  * **offline** — falls back to bundled fixtures (real captured responses) so the
                  full pipeline and demo work with no key.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from alphatide.core.cache import TTLCache
from alphatide.core.config import settings
from alphatide.core.models import AddressLabel

BASE_URL = "https://api.asksurf.ai/gateway/v1"
BATCH_LIMIT = 100
_FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "surf_labels.json"


class QuotaExhausted(RuntimeError):
    """Raised when the Surf free/paid credit balance is used up."""


class SurfClient:
    def __init__(
        self,
        api_key: str | None = None,
        offline: bool | None = None,
        cache: TTLCache | None = None,
        budget=None,
    ) -> None:
        self.api_key = api_key if api_key is not None else settings.surf_api_key
        # offline auto-on only as a *fallback*; live is attempted first unless forced.
        self.offline = bool(offline)
        self.cache = cache or TTLCache(settings.label_cache_ttl)
        # Optional DailyCreditBudget — when set, live spend is gated by it.
        self.budget = budget
        self.credits_used = 0
        self._fixtures = self._load_fixtures()

    @staticmethod
    def _load_fixtures() -> dict[str, dict]:
        if _FIXTURES.exists():
            data = json.loads(_FIXTURES.read_text(encoding="utf-8"))
            return {k.lower(): v for k, v in data.get("labels", {}).items()}
        return {}

    # --- HTTP ---
    def _get(self, path: str, params: dict) -> dict:
        qs = urllib.parse.urlencode(params)
        req = urllib.request.Request(f"{BASE_URL}{path}?{qs}")
        if self.api_key:
            req.add_header("Authorization", f"Bearer {self.api_key}")
        try:
            with urllib.request.urlopen(req, timeout=40) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            body = e.read().decode(errors="replace")
            if e.code == 402 or "QUOTA_EXHAUSTED" in body or "BALANCE_ZERO" in body:
                raise QuotaExhausted(body) from e
            raise

    # --- labels ---
    def label_addresses(self, addresses: list[str]) -> dict[str, AddressLabel]:
        """Resolve labels for many addresses. Cache-first, batched, mode-aware."""
        norm = [a.lower() for a in addresses]
        result: dict[str, AddressLabel] = {}

        # 1) serve from cache
        to_fetch: list[str] = []
        for a in norm:
            cached = self.cache.get(a)
            if cached is not None:
                result[a] = AddressLabel(**cached) if isinstance(cached, dict) else cached
            elif a not in to_fetch:
                to_fetch.append(a)

        if not to_fetch:
            return result

        # 2) fetch the rest (live, falling back to fixtures)
        if self.offline:
            fetched = self._label_offline(to_fetch)
        elif self.budget is not None and not self.budget.can_spend(1):
            # daily credit ceiling reached → degrade to fixtures, keep responding
            fetched = self._label_offline(to_fetch)
        else:
            try:
                fetched = self._label_live(to_fetch)
            except QuotaExhausted:
                # graceful fallback: serve what fixtures know, mark the rest empty
                fetched = self._label_offline(to_fetch)

        for a, label in fetched.items():
            # cache as dict for JSON-persistability
            self.cache.set(
                a,
                {
                    "address": label.address,
                    "entity_name": label.entity_name,
                    "entity_type": label.entity_type,
                    "labels": label.labels,
                    "confidence": label.confidence,
                },
            )
            result[a] = label
        return result

    def _label_live(self, addresses: list[str]) -> dict[str, AddressLabel]:
        out: dict[str, AddressLabel] = {}
        for i in range(0, len(addresses), BATCH_LIMIT):
            chunk = addresses[i : i + BATCH_LIMIT]
            # stop spending mid-way if the daily ceiling is hit; rest via fixtures
            if self.budget is not None and not self.budget.can_spend(1):
                out.update(self._label_offline(chunk))
                continue
            resp = self._get(
                "/wallet/labels/batch", {"addresses": ",".join(chunk)}
            )
            credits = int(resp.get("meta", {}).get("credits_used", 0))
            self.credits_used += credits
            if self.budget is not None:
                self.budget.record(credits)
            seen = set()
            for item in resp.get("data", []):
                label = AddressLabel.from_surf(item)
                out[label.address] = label
                seen.add(label.address)
            # addresses with no record still get a definitive empty answer (cacheable)
            for a in chunk:
                if a not in seen:
                    out[a] = AddressLabel.empty(a)
        return out

    def _label_offline(self, addresses: list[str]) -> dict[str, AddressLabel]:
        out: dict[str, AddressLabel] = {}
        for a in addresses:
            fx = self._fixtures.get(a)
            out[a] = AddressLabel.from_surf(fx) if fx else AddressLabel.empty(a)
        return out

    # --- optional enrichment (used only on confirmed hits) ---
    def wallet_detail(self, address: str) -> dict | None:
        if self.offline or not self.api_key:
            return None
        try:
            resp = self._get(
                "/wallet/detail", {"address": address, "fields": "labels,balance"}
            )
            self.credits_used += int(resp.get("meta", {}).get("credits_used", 0))
            return resp.get("data")
        except (QuotaExhausted, urllib.error.HTTPError):
            return None
