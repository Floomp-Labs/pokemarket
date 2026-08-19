"""TCGdex client: free, keyless community API (api.tcgdex.net).

Card detail payloads carry a `pricing` block with both TCGplayer (USD,
per-variant low/mid/high/market/directLow) and Cardmarket (EUR averages)
sections. Set and card ids differ from pokemontcg.io, so we resolve a
tracked card once (set-name similarity + name/localId search) and cache
the TCGdex id on the Card row.
"""

import asyncio
import logging
import re
import time
from typing import Optional

import httpx

log = logging.getLogger(__name__)

BASE = "https://api.tcgdex.net/v2/en"

_SETS_TTL = 24 * 3600

# pokemontcg price_type -> TCGdex pricing.tcgplayer key
_VARIANT_KEY = {
    "normal": "normal",
    "holofoil": "holofoil",
    "reverseHolofoil": "reverse-holofoil",
    "1stEditionNormal": "1st-edition",
    "1stEditionHolofoil": "1st-edition-holofoil",
}


def _tokens(s: str) -> set[str]:
    return {t for t in re.sub(r"[^a-z0-9 ]", " ", s.lower()).split() if t}


def _jaccard(a: set[str], b: set[str]) -> float:
    union = a | b
    return len(a & b) / len(union) if union else 0.0


class TCGdexClient:
    def __init__(self) -> None:
        self._client = httpx.AsyncClient(base_url=BASE, timeout=20.0)
        self._sets: tuple[float, list[dict]] | None = None

    async def close(self) -> None:
        await self._client.aclose()

    async def _get(self, path: str, params: Optional[dict] = None):
        delay = 1.0
        for attempt in range(3):
            try:
                resp = await self._client.get(path, params=params)
                if resp.status_code == 429 or resp.status_code >= 500:
                    raise httpx.HTTPStatusError(
                        f"retryable status {resp.status_code}",
                        request=resp.request,
                        response=resp,
                    )
                resp.raise_for_status()
                return resp.json()
            except httpx.HTTPError:
                if attempt == 2:
                    raise
                log.warning("tcgdex retry %d for %s", attempt + 1, path)
                await asyncio.sleep(delay)
                delay *= 2
        raise RuntimeError("unreachable")

    async def sets(self) -> list[dict]:
        if self._sets and time.monotonic() - self._sets[0] < _SETS_TTL:
            return self._sets[1]
        results = await self._get("/sets")
        self._sets = (time.monotonic(), results)
        return results

    async def match_card(
        self, name: str, number: Optional[str], set_name: str
    ) -> Optional[str]:
        want_set = _tokens(set_name) - {"pokemon"}
        set_id = None
        best = 0.45
        for s in await self.sets():
            score = _jaccard(want_set, _tokens(s.get("name") or ""))
            if score > best:
                set_id, best = s["id"], score

        params = {"name": name}
        if number:
            params["localId"] = number
        try:
            candidates = await self._get("/cards", params=params)
        except httpx.HTTPError:
            return None
        if not isinstance(candidates, list) or not candidates:
            return None

        name_l = name.lower()
        exact = [c for c in candidates if (c.get("name") or "").lower() == name_l]
        pool = exact or candidates
        if set_id:
            for c in pool:
                if (c.get("id") or "").startswith(f"{set_id}-"):
                    return c["id"]
        return pool[0].get("id")

    async def price_for(
        self, card_id: str, price_type: Optional[str]
    ) -> tuple[Optional[dict], Optional[dict]]:
        """-> (usd_block, cm_block). usd_block uses our snapshot field names."""
        detail = await self._get(f"/cards/{card_id}")
        pricing = detail.get("pricing") or {}

        usd = None
        tp = pricing.get("tcgplayer") or {}
        key = _VARIANT_KEY.get(price_type or "")
        block = tp.get(key) if key else None
        if block is None:
            block = tp.get("normal") or next(
                (b for b in tp.values() if isinstance(b, dict) and b.get("marketPrice")),
                None,
            )
        if block and block.get("marketPrice") is not None:
            usd = {
                "market": block.get("marketPrice"),
                "low": block.get("lowPrice"),
                "mid": block.get("midPrice"),
                "high": block.get("highPrice"),
                "direct_low": block.get("directLowPrice"),
            }

        cm_raw = pricing.get("cardmarket") or {}
        cm = None
        if cm_raw.get("trend") is not None:
            cm = {
                "cm_avg1": cm_raw.get("avg1"),
                "cm_avg7": cm_raw.get("avg7"),
                "cm_avg30": cm_raw.get("avg30"),
                "cm_trend": cm_raw.get("trend"),
                "cm_avg_sell": cm_raw.get("avg"),
                "cm_low": cm_raw.get("low"),
            }
        return usd, cm
