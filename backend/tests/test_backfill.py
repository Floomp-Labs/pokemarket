import json

from sqlmodel import SQLModel, Session, create_engine, select

from app.models import PriceSnapshot
from app.service import backfill_card_anchors


def make_session():
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    return Session(engine)


def test_backfill_creates_7d_and_30d_estimated_anchors():
    with make_session() as s:
        cm = {"trendPrice": 100.0, "avg7": 90.0, "avg30": 80.0, "avg1": 300.0}
        tcg = {"holofoil": {"market": 200.0}, "normal": {"market": 150.0}}
        added = backfill_card_anchors(s, "x-1", 200.0, cm, tcg)
        rows = s.exec(select(PriceSnapshot)).all()

        assert added == 2  # avg1 must never produce an anchor
        assert all(r.estimated for r in rows)
        markets = sorted(r.market for r in rows)
        assert markets == [160.0, 180.0]  # 200 * 0.8, 200 * 0.9

        variants = json.loads(rows[0].variants_json)
        assert set(variants) == {"holofoil", "normal"}


def test_backfill_clamps_extreme_ratios():
    with make_session() as s:
        cm = {"trendPrice": 100.0, "avg7": 500.0, "avg30": 5.0}
        added = backfill_card_anchors(s, "x-1", 200.0, cm)
        rows = s.exec(select(PriceSnapshot)).all()

        assert added == 2
        markets = sorted(r.market for r in rows)
        assert markets == [100.0, 400.0]  # clamped to 0.5x and 2.0x


def test_backfill_skips_when_no_cardmarket_data():
    with make_session() as s:
        assert backfill_card_anchors(s, "x-1", 200.0, {}) == 0
        assert backfill_card_anchors(s, "x-1", 0, {"trendPrice": 1.0}) == 0
