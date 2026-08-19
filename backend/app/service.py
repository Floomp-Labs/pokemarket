import json
import re
import statistics
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlmodel import Session

from .models import Card, PriceSnapshot, Product, ProductSnapshot, utcnow
from .pricecharting_client import PriceChartingClient
from .tcg_client import TCGClient, pick_price_type

_NUM_RE = re.compile(r"#([A-Za-z0-9]+)")
_VARIANT_RE = re.compile(r"\[[^\]]+\]")


def compile_sources(sources: dict[str, dict]) -> dict:
    """Median of each numeric field across every source that reported it.

    Sources are independent snapshots of (mostly) the same marketplaces, so
    the median dampens single-source outliers and stale scrapes.
    """
    out = {}
    for field in ("market", "low", "mid", "high", "direct_low"):
        vals = [v for s in sources.values() if (v := s.get(field)) is not None]
        if vals:
            out[field] = round(statistics.median(vals), 4)
    return out


def _tokens(s: str) -> set[str]:
    return {t for t in re.sub(r"[^a-z0-9 ]", " ", s.lower()).split() if t}


def match_card_page(
    results: list[dict], name: str, number: Optional[str], set_name: str
) -> Optional[str]:
    """Pick the PriceCharting search result that is exactly this card.

    Candidates must carry the same card number and contain the card name;
    ties are broken by set-name similarity (Jaccard) with a penalty for
    variant printings like "[1st Edition]" / "[Shadowless]".
    """
    name_t = _tokens(name)
    set_t = _tokens(set_name) - {"pokemon"}
    want_num = number.lower() if number else None
    best_url, best_score = None, 0.0
    for r in results:
        clean = _VARIANT_RE.sub("", r["name"])
        variant = clean != r["name"]
        num_m = _NUM_RE.search(clean)
        cand_num = num_m.group(1).lower() if num_m else None
        cand_name_t = _tokens(_NUM_RE.sub("", clean))
        if name_t and not name_t.issubset(cand_name_t):
            continue
        if want_num and cand_num != want_num:
            continue
        cand_set_t = _tokens(r.get("set_name") or "") - {"pokemon"}
        union = set_t | cand_set_t
        score = (len(set_t & cand_set_t) / len(union)) if union else 0.0
        if want_num:
            score += 1.0
        if variant:
            score -= 0.5
        if score > best_score:
            best_score, best_url = score, r["url"]
    return best_url


async def match_card_pc_url(
    client: PriceChartingClient, name: str, number: Optional[str], set_name: str
) -> Optional[str]:
    # PriceCharting search is literal: a full "name number set" query often
    # returns nothing even when the exact card exists. Fall back to looser
    # queries; match_card_page still enforces number + name + set similarity.
    queries = [
        " ".join(part for part in (name, number, set_name) if part),
        " ".join(part for part in (name, set_name) if part),
        name,
    ]
    for q in dict.fromkeys(queries):
        results = await client.search_products(q)
        url = match_card_page(results, name, number, set_name)
        if url:
            return url
    return None


def backfill_card_anchors(
    session: Session,
    card_id: str,
    current_market: float,
    cm_prices: dict,
    tcg_prices: Optional[dict] = None,
    now: Optional[datetime] = None,
) -> int:
    """Insert estimated -7d/-30d anchor points.

    pokemontcg.io has no historical endpoint, so we scale the current USD
    market price by Cardmarket's avg7/avg30 relative to its trend price.
    avg1 is excluded: single-day averages on vintage cards are dominated by
    one-off high-value sales and produce absurd anchors. Ratios are clamped
    as a sanity guard. When the full tcgplayer prices block is available,
    per-variant market estimates are stored too. Anchors are flagged
    estimated=True so the UI can distinguish them.
    """
    if not current_market:
        return 0
    trend = cm_prices.get("trendPrice") or cm_prices.get("avg7") or cm_prices.get("avg1")
    if not trend:
        return 0
    now = now or utcnow()
    added = 0
    for days, key in ((7, "avg7"), (30, "avg30")):
        avg = cm_prices.get(key)
        if not avg:
            continue
        ratio = min(2.0, max(0.5, avg / trend))
        est = round(current_market * ratio, 4)
        variants_est = {}
        for pt, block in (tcg_prices or {}).items():
            m = (block or {}).get("market")
            if m:
                variants_est[pt] = {"market": round(m * ratio, 4)}
        session.add(
            PriceSnapshot(
                card_id=card_id,
                ts=now - timedelta(days=days),
                market=est,
                variants_json=json.dumps(variants_est) if variants_est else None,
                estimated=True,
            )
        )
        added += 1
    return added


async def add_card_from_api(client: TCGClient, session: Session, card_id: str) -> Card:
    """Fetch a card from pokemontcg.io, insert it into the watchlist, take an
    initial snapshot, and backfill 30-day estimated anchors."""
    data = await client.get_card(card_id)
    prices = (data.get("tcgplayer") or {}).get("prices") or {}
    price_type = pick_price_type(prices) or "normal"

    card = Card(
        id=data["id"],
        name=data["name"],
        set_id=data["set"]["id"],
        set_name=data["set"]["name"],
        number=data["number"],
        rarity=data.get("rarity"),
        image_small=(data.get("images") or {}).get("small"),
        image_large=(data.get("images") or {}).get("large"),
        price_type=price_type,
    )
    session.add(card)

    block = prices.get(price_type) or {}
    market = block.get("market")
    cm = (data.get("cardmarket") or {}).get("prices") or {}
    if market is not None:
        session.add(
            PriceSnapshot(
                card_id=card.id,
                low=block.get("low"),
                mid=block.get("mid"),
                high=block.get("high"),
                market=market,
                direct_low=block.get("directLow"),
                source_updated_at=(data.get("tcgplayer") or {}).get("updatedAt"),
                cm_avg1=cm.get("avg1"),
                cm_avg7=cm.get("avg7"),
                cm_avg30=cm.get("avg30"),
                cm_trend=cm.get("trendPrice"),
                cm_avg_sell=cm.get("averageSellPrice"),
                cm_low=cm.get("lowPrice"),
                variants_json=json.dumps(prices) if prices else None,
            )
        )
        backfill_card_anchors(session, card.id, market, cm, prices)
    session.commit()
    session.refresh(card)
    return card


@dataclass
class ProductMeta:
    id: str
    name: str
    set_name: Optional[str]
    url: str
    image_small: Optional[str]
    used: Optional[float]
    cib: Optional[float]
    new: Optional[float]

    def best_kind(self) -> str:
        if self.new is not None:
            return "new"
        if self.cib is not None:
            return "cib"
        return "used"

    def price_for(self, kind: str) -> Optional[float]:
        return {"new": self.new, "cib": self.cib, "used": self.used}.get(kind)


async def add_product_from_meta(
    client: PriceChartingClient, session: Session, meta: ProductMeta
) -> Product:
    """Insert a sealed product and backfill its full monthly price history
    from the product page's embedded chart data (real PriceCharting data)."""
    kind = meta.best_kind()
    product = Product(
        id=meta.id,
        name=meta.name,
        set_name=meta.set_name,
        url=meta.url,
        image_small=meta.image_small,
        price_kind=kind,
    )
    session.add(product)

    series = await client.get_history(meta.url)
    points = [(t, cents) for t, cents in series.get(kind, []) if cents]
    for t, cents in points[-120:]:
        ts = datetime.fromtimestamp(t / 1000, tz=timezone.utc).replace(tzinfo=None)
        session.add(
            ProductSnapshot(
                product_id=product.id,
                ts=ts,
                price=round(cents / 100.0, 2),
                estimated=False,
            )
        )
    if not points:
        # No chart history; fall back to the current price from search.
        current = meta.price_for(kind)
        if current is not None:
            session.add(
                ProductSnapshot(product_id=product.id, price=current, estimated=False)
            )
    session.commit()
    session.refresh(product)
    return product
