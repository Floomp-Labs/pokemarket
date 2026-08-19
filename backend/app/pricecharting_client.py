"""PriceCharting client for sealed products (booster boxes, ETBs, packs).

Two data planes, both scraped from public pages:
- search-products returns an HTML table with current used/cib/new prices
- each product page embeds VGPC.chart_data: monthly [epoch_ms, cents] series
"""

import asyncio
import html as html_lib
import json
import logging
import re
from typing import Optional

import httpx

log = logging.getLogger(__name__)

BASE = "https://www.pricecharting.com"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
    )
}

_ROW_RE = re.compile(r'<tr[^>]*id="product-(\d+)"[^>]*>(.*?)</tr>', re.S)
_TITLE_RE = re.compile(r'<td class="title">\s*<a href="([^"]+)"[^>]*>\s*(.*?)</a>', re.S)
_IMG_RE = re.compile(r'<img class="photo"[^>]*src="([^"]+)"')
_CONSOLE_RE = re.compile(r'<td class="console[^"]*"[^>]*>(.*?)</td>', re.S)
_TAG_RE = re.compile(r"<[^>]+>")
_FULL_PRICE_ROW_RE = re.compile(
    r'<tr>\s*<td>([^<]+)</td>\s*<td class="price js-price">([^<]*)</td>', re.S
)

# Full Price Guide labels -> our grade keys. Mid grades are labelled "Grade N"
# on PriceCharting; for TCG cards those tiers aggregate (almost entirely PSA)
# graded sales. We keep the PSA-relevant rows only.
_GRADE_LABELS = {"Ungraded": "ungraded", "Grade 9.5": "9.5", "PSA 10": "10"}
_GRADE_LABELS.update({f"Grade {n}": str(n) for n in range(1, 10)})


def _money(text: str) -> Optional[float]:
    text = _TAG_RE.sub("", text).strip().replace("$", "").replace(",", "")
    if not text or text in ("—", "-"):
        return None
    try:
        return float(text)
    except ValueError:
        return None


def parse_search_page(html: str) -> list[dict]:
    out = []
    for pid, row in _ROW_RE.findall(html):
        title = _TITLE_RE.search(row)
        if not title:
            continue
        url = html_lib.unescape(title.group(1))
        name = html_lib.unescape(re.sub(r"\s+", " ", _TAG_RE.sub("", title.group(2))).strip())
        img = _IMG_RE.search(row)
        console = _CONSOLE_RE.search(row)
        prices = {}
        for kind in ("used", "cib", "new"):
            m = re.search(rf'<td class="price numeric {kind}_price"[^>]*>(.*?)</td>', row, re.S)
            prices[kind] = _money(m.group(1)) if m else None
        out.append(
            {
                "id": pid,
                "name": name,
                "url": url,
                "set_name": (
                    html_lib.unescape(_TAG_RE.sub("", console.group(1)).strip())
                    if console
                    else None
                ),
                "image_small": img.group(1) if img else None,
                "used": prices["used"],
                "cib": prices["cib"],
                "new": prices["new"],
            }
        )
    return out


def parse_chart_data(html: str) -> dict[str, list[tuple[int, float]]]:
    """Extract VGPC.chart_data via brace balancing; values are [epoch_ms, cents]."""
    i = html.find("VGPC.chart_data")
    if i < 0:
        return {}
    start = html.find("{", i)
    if start < 0:
        return {}
    depth = 0
    for j in range(start, len(html)):
        c = html[j]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                try:
                    raw = json.loads(html[start : j + 1])
                except json.JSONDecodeError:
                    return {}
                return {
                    k: [(int(t), float(p)) for t, p in v]
                    for k, v in raw.items()
                    if isinstance(v, list)
                }
    return {}


def parse_full_prices(html: str) -> dict[str, float]:
    """Extract the Full Price Guide from a card page: PSA 1-10 plus ungraded.

    Rows look like `<tr><td>Grade 7</td><td class="price js-price">$781.00</td>`.
    The guide is the first table inside the full-prices div; the label
    whitelist additionally keeps unrelated rows from leaking in.
    """
    start = html.find('id="full-prices"')
    if start < 0:
        return {}
    end = html.find("</table>", start)
    section = html[start:] if end < 0 else html[start:end]
    out: dict[str, float] = {}
    for label, price_text in _FULL_PRICE_ROW_RE.findall(section):
        key = _GRADE_LABELS.get(label.strip())
        if key is None:
            continue
        price = _money(price_text)
        if price is not None:
            out[key] = price
    return out


class PriceChartingClient:
    def __init__(self) -> None:
        self._client = httpx.AsyncClient(
            base_url=BASE, headers=HEADERS, timeout=25.0, follow_redirects=True
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def _get(self, path: str, params: Optional[dict] = None) -> str:
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
                return resp.text
            except httpx.HTTPError:
                if attempt == 2:
                    raise
                log.warning("pricecharting retry %d for %s", attempt + 1, path)
                await asyncio.sleep(delay)
                delay *= 2
        raise RuntimeError("unreachable")

    async def search_products(self, q: str) -> list[dict]:
        html = await self._get("/search-products", params={"q": q, "type": "prices"})
        return parse_search_page(html)

    async def get_history(self, url: str) -> dict[str, list[tuple[int, float]]]:
        path = url.replace(BASE, "") if url.startswith(BASE) else url
        html = await self._get(path)
        return parse_chart_data(html)

    async def get_current_price(self, url: str, kind: str) -> Optional[float]:
        """Latest nonzero point of the tracked series, in dollars."""
        series = await self.get_history(url)
        for _ts, cents in reversed(series.get(kind, [])):
            if cents:
                return round(cents / 100.0, 2)
        return None

    async def get_grade_prices(self, url: str) -> dict[str, float]:
        """Full Price Guide (PSA 1-10 + ungraded) for a card page, in dollars."""
        path = url.replace(BASE, "") if url.startswith(BASE) else url
        html = await self._get(path)
        return parse_full_prices(html)
