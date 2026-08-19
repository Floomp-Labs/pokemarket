from datetime import datetime, timezone
from typing import Optional

from sqlmodel import Field, SQLModel


def utcnow() -> datetime:
    # Naive UTC everywhere: SQLite returns naive datetimes, and mixing
    # tz-aware/naive breaks comparisons.
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Card(SQLModel, table=True):
    id: str = Field(primary_key=True)  # pokemontcg.io id, e.g. "swsh4-25"
    name: str
    set_id: str
    set_name: str
    number: str
    rarity: Optional[str] = None
    image_small: Optional[str] = None
    image_large: Optional[str] = None
    price_type: str = "normal"  # tcgplayer price block we track
    pc_url: Optional[str] = None  # matched PriceCharting card page
    pc_match_attempted: bool = False  # only auto-search PriceCharting once
    tcgcsv_group_id: Optional[int] = None  # resolved TCGCSV set
    tcgcsv_product_id: Optional[int] = None  # resolved TCGCSV product
    tcgcsv_match_attempted: bool = False
    tcgdex_id: Optional[str] = None  # resolved TCGdex card id
    tcgdex_match_attempted: bool = False
    added_at: datetime = Field(default_factory=utcnow)


class PriceSnapshot(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    card_id: str = Field(foreign_key="card.id", index=True)
    ts: datetime = Field(default_factory=utcnow, index=True)
    low: Optional[float] = None
    mid: Optional[float] = None
    high: Optional[float] = None
    market: Optional[float] = None
    direct_low: Optional[float] = None
    source_updated_at: Optional[str] = None
    # Cardmarket 1/7/30-day average sale prices (EUR), captured per poll.
    cm_avg1: Optional[float] = None
    cm_avg7: Optional[float] = None
    cm_avg30: Optional[float] = None
    cm_trend: Optional[float] = None
    cm_avg_sell: Optional[float] = None
    cm_low: Optional[float] = None
    # Full tcgplayer prices block (all variants: normal/holofoil/...), as JSON.
    variants_json: Optional[str] = None
    # Per-source prices used for the compiled consensus, as JSON:
    # {"pokemontcg": {"market": ...}, "tcgcsv": {...}, "tcgdex": {...}}
    sources_json: Optional[str] = None
    # True for backfilled anchor points derived from Cardmarket trend ratios.
    estimated: bool = False


class GradeSnapshot(SQLModel, table=True):
    """One card's PSA 1-10 (+ ungraded) price guide at a point in time.

    prices_json maps grade key -> USD price, e.g. {"ungraded": 405.0,
    "1": 370.0, ..., "9.5": 6086.0, "10": 28112.98}. Scraped from the
    PriceCharting Full Price Guide on the card's matched page.
    """

    id: Optional[int] = Field(default=None, primary_key=True)
    card_id: str = Field(foreign_key="card.id", index=True)
    ts: datetime = Field(default_factory=utcnow, index=True)
    prices_json: str


class Product(SQLModel, table=True):
    """A sealed product (booster box, ETB, pack) tracked via PriceCharting."""

    id: str = Field(primary_key=True)  # pricecharting product id
    name: str
    set_name: Optional[str] = None  # e.g. "Pokemon Scarlet & Violet"
    url: str
    image_small: Optional[str] = None
    price_kind: str = "new"  # which price column we track: new | cib | used
    tcgcsv_group_id: Optional[int] = None  # resolved TCGCSV set
    tcgcsv_product_id: Optional[int] = None  # resolved TCGCSV sealed product
    tcgcsv_match_attempted: bool = False
    added_at: datetime = Field(default_factory=utcnow)


class ProductSnapshot(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    product_id: str = Field(foreign_key="product.id", index=True)
    ts: datetime = Field(default_factory=utcnow, index=True)
    price: float
    # {"pricecharting": {"market": ...}, "tcgcsv": {...}}
    sources_json: Optional[str] = None
    estimated: bool = False


class Alert(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    subject_id: str = Field(index=True)  # card id or product id
    subject_type: str = "card"  # card | product
    ts: datetime = Field(default_factory=utcnow)
    kind: str  # spike | drop | trend_reversal
    severity: str  # warn | critical
    pct_change: float
    z_score: Optional[float] = None
    message: str
    acknowledged: bool = False
