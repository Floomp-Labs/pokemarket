import asyncio
import logging
from typing import Any, Optional

import httpx

from .config import settings

log = logging.getLogger(__name__)

BASE_URL = "https://api.pokemontcg.io/v2"

# Most valuable/liquid printing first; fall back to whatever has a market price.
PRICE_TYPE_PREFERENCE = [
    "1stEditionHolofoil",
    "holofoil",
    "reverseHolofoil",
    "1stEditionNormal",
    "normal",
]


def pick_price_type(prices: dict[str, Any]) -> Optional[str]:
    for pt in PRICE_TYPE_PREFERENCE:
        block = prices.get(pt)
        if block and block.get("market") is not None:
            return pt
    for pt, block in prices.items():
        if block and block.get("market") is not None:
            return pt
    return None


class TCGClient:
    def __init__(self) -> None:
        headers = {}
        if settings.pokemontcg_api_key:
            headers["X-Api-Key"] = settings.pokemontcg_api_key
        self._client = httpx.AsyncClient(base_url=BASE_URL, headers=headers, timeout=20.0)

    async def close(self) -> None:
        await self._client.aclose()

    async def _get(self, path: str, params: Optional[dict] = None) -> dict:
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
                log.warning("tcg api retry %d for %s", attempt + 1, path)
                await asyncio.sleep(delay)
                delay *= 2
        raise RuntimeError("unreachable")

    async def get_card(self, card_id: str) -> dict:
        payload = await self._get(f"/cards/{card_id}")
        return payload["data"]

    async def search_cards(self, query: str, page_size: int = 12) -> list[dict]:
        payload = await self._get(
            "/cards",
            params={"q": query, "pageSize": page_size, "orderBy": "-set.releaseDate"},
        )
        return payload.get("data", [])
