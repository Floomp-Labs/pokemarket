"""TCGCSV client: free daily mirror of the full TCGplayer catalog.

No API key. Three JSON endpoints per game (Pokemon is categoryId 3):
- groups:    /tcgplayer/3/groups                    -> sets
- products:  /tcgplayer/3/{groupId}/products        -> cards AND sealed
- prices:    /tcgplayer/3/{groupId}/prices          -> per productId+variant

Products carry extendedData (Number, Rarity, ...) which we use to match
tracked cards; sealed products are matched by name tokens. Responses are
cached in-memory: groups/products for hours, prices for one collect cycle.
"""

import asyncio
import logging
import re
import time
from typing import Optional

import httpx

log = logging.getLogger(__name__)

BASE = "https://tcgcsv.com/tcgplayer/3"

# tcgcsv.com 401s generic HTTP-client user agents; present as a browser.
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
    )
}

_GROUPS_TTL = 12 * 3600
_PRODUCTS_TTL = 12 * 3600
_PRICES_TTL = 20 * 60

# pokemontcg price_type -> TCGCSV subTypeName
_SUBTYPE = {
    "normal": "Normal",
    "holofoil": "Holofoil",
    "reverseHolofoil": "Reverse Holofoil",
    "1stEditionNormal": "1st Edition",
    "1stEditionHolofoil": "1st Edition Holofoil",
}

_SERIES_CODE_RE = re.compile(r"^(swsh|sv|sm|xy|bw|dp|ex|neo|me|a)\d*[a-z]?$")
_PARENS_RE = re.compile(r"\([^)]*\)")


def _tokens(s: str) -> set[str]:
    return {t for t in re.sub(r"[^a-z0-9 ]", " ", s.lower()).split() if t}


def _group_tokens(name: str) -> set[str]:
    # Drop series codes ("swsh04", "sv", "me05") so they don't dilute
    # similarity against pokemontcg set names, which omit them.
    return {t for t in _tokens(name) if not _SERIES_CODE_RE.match(t)}


def _norm_number(s: Optional[str]) -> Optional[str]:
    """'044/185' -> '44', 'TG11/TG30' -> 'TG11', '025' -> '25'."""
    if not s:
        return None
    part = s.split("/")[0].strip().upper()
    if part.isdigit():
        part = part.lstrip("0") or "0"
    return part or None


def _jaccard(a: set[str], b: set[str]) -> float:
    union = a | b
    return len(a & b) / len(union) if union else 0.0


class TCGCSVClient:
    def __init__(self) -> None:
        self._client = httpx.AsyncClient(timeout=30.0, headers=HEADERS)
        self._groups: tuple[float, list[dict]] | None = None
        self._products: dict[int, tuple[float, list[dict]]] = {}
        self._prices: dict[int, tuple[float, dict[int, list[dict]]]] = {}
        self._last_request = 0.0

    async def close(self) -> None:
        await self._client.aclose()

    async def _get(self, path: str) -> dict:
        # TCGCSV asks for ~1 req/sec; caches keep us well under that.
        gap = time.monotonic() - self._last_request
        if gap < 0.5:
            await asyncio.sleep(0.5 - gap)
        delay = 1.0
        for attempt in range(3):
            try:
                self._last_request = time.monotonic()
                resp = await self._client.get(f"{BASE}{path}")
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
                log.warning("tcgcsv retry %d for %s", attempt + 1, path)
                await asyncio.sleep(delay)
                delay *= 2
        raise RuntimeError("unreachable")

    async def groups(self) -> list[dict]:
        if self._groups and time.monotonic() - self._groups[0] < _GROUPS_TTL:
            return self._groups[1]
        payload = await self._get("/groups")
        results = payload.get("results", [])
        self._groups = (time.monotonic(), results)
        return results

    async def products(self, group_id: int) -> list[dict]:
        cached = self._products.get(group_id)
        if cached and time.monotonic() - cached[0] < _PRODUCTS_TTL:
            return cached[1]
        payload = await self._get(f"/{group_id}/products")
        results = payload.get("results", [])
        self._products[group_id] = (time.monotonic(), results)
        return results

    async def prices(self, group_id: int) -> dict[int, list[dict]]:
        cached = self._prices.get(group_id)
        if cached and time.monotonic() - cached[0] < _PRICES_TTL:
            return cached[1]
        payload = await self._get(f"/{group_id}/prices")
        by_product: dict[int, list[dict]] = {}
        for row in payload.get("results", []):
            by_product.setdefault(row["productId"], []).append(row)
        self._prices[group_id] = (time.monotonic(), by_product)
        return by_product

    def match_group(self, groups: list[dict], set_name: str) -> Optional[int]:
        # Ties are common ("Base Set" vs "SM Base Set"): prefer the group
        # with fewer raw tokens (no extra prefix/qualifiers), then the oldest.
        want = _tokens(set_name) - {"pokemon"}
        best_id, best_key = None, None
        ordered = sorted(groups, key=lambda g: g.get("publishedOn") or "")
        for g in ordered:
            cand = _group_tokens(g.get("name") or "")
            score = _jaccard(want, cand)
            if score < 0.45:
                continue
            key = (score, -len(_tokens(g.get("name") or "")))
            if best_key is None or key > best_key:
                best_id, best_key = g["groupId"], key
        return best_id

    def match_card_product(
        self, products: list[dict], name: str, number: Optional[str]
    ) -> Optional[int]:
        want_num = _norm_number(number)
        name_t = _tokens(name)
        best_id, best_score = None, 0.0
        for p in products:
            ed = {e["name"]: e.get("value") for e in p.get("extendedData", [])}
            if "Number" not in ed:
                continue  # sealed product, not a card
            if want_num and _norm_number(ed["Number"]) != want_num:
                continue
            cand_name_t = _tokens(_PARENS_RE.sub("", p["name"]))
            if name_t and not name_t.issubset(cand_name_t):
                continue
            score = _jaccard(name_t, cand_name_t) + (1.0 if want_num else 0.0)
            if score > best_score:
                best_id, best_score = p["productId"], score
        return best_id

    def match_sealed_product(
        self, products: list[dict], name: str, set_name: Optional[str]
    ) -> Optional[int]:
        want = _tokens(name) | (_tokens(set_name or "") - {"pokemon"})
        if not want:
            return None
        best_id, best_score = None, 0.6
        for p in products:
            ed = {e["name"]: e.get("value") for e in p.get("extendedData", [])}
            if "Number" in ed:
                continue  # single card, not sealed
            cand = _tokens(_PARENS_RE.sub("", p["name"]))
            score = _jaccard(want, cand)
            if score > best_score:
                best_id, best_score = p["productId"], score
        return best_id

    async def resolve_card(
        self, name: str, number: Optional[str], set_name: str
    ) -> tuple[Optional[int], Optional[int]]:
        """-> (group_id, product_id), either may be None when unmatched."""
        groups = await self.groups()
        gid = self.match_group(groups, set_name)
        if gid is None:
            return None, None
        products = await self.products(gid)
        return gid, self.match_card_product(products, name, number)

    async def resolve_sealed(
        self, name: str, set_name: Optional[str]
    ) -> tuple[Optional[int], Optional[int]]:
        groups = await self.groups()
        gid = self.match_group(groups, set_name or "")
        if gid is None:
            return None, None
        products = await self.products(gid)
        return gid, self.match_sealed_product(products, name, set_name)

    async def price_for(
        self, group_id: int, product_id: int, price_type: Optional[str] = None
    ) -> Optional[dict]:
        rows = (await self.prices(group_id)).get(product_id) or []
        if not rows:
            return None
        row = None
        want_sub = _SUBTYPE.get(price_type or "")
        if want_sub:
            row = next((r for r in rows if r.get("subTypeName") == want_sub), None)
        if row is None:
            row = next((r for r in rows if r.get("subTypeName") == "Normal"), rows[0])
        if row.get("marketPrice") is None:
            return None
        return {
            "market": row.get("marketPrice"),
            "low": row.get("lowPrice"),
            "mid": row.get("midPrice"),
            "high": row.get("highPrice"),
            "direct_low": row.get("directLowPrice"),
        }
