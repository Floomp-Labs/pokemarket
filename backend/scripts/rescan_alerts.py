"""Replay stored snapshots through the anomaly detector with the current
thresholds, rebuilding the alerts table: python -m scripts.rescan_alerts

Existing alerts are wiped so the feed reflects exactly what the detector
fires on the recorded history (no duplicates vs. live collection).

All inserts happen in a single session/transaction: mixing an outer read
session with per-subject write sessions self-locks sqlite.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlmodel import Session, select

from app.agent.detector import (
    detect_anomaly,
    detect_regional_spread,
    detect_source_spread,
)
from app.config import settings
from app.db import engine, init_db
from app.models import Alert, Card, PriceSnapshot, Product, ProductSnapshot


def _add(session, subject_id, subject_type, ts, d) -> None:
    session.add(
        Alert(
            subject_id=subject_id,
            subject_type=subject_type,
            ts=ts,
            kind=d.kind,
            severity=d.severity,
            pct_change=d.pct_change,
            z_score=d.z_score,
            message=d.message,
        )
    )


def rescan(session, subject_id: str, subject_type: str, label: str, snaps, price_of) -> int:
    history: list = []
    last_alert = None
    count = 0
    for snap in snaps:
        price = price_of(snap)
        if price is None:
            continue
        d = detect_anomaly(
            label,
            history,
            price,
            pct_threshold=settings.alert_pct_threshold,
            z_threshold=settings.alert_z_threshold,
            cooldown_minutes=settings.alert_cooldown_minutes,
            last_alert_ts=last_alert,
            now=snap.ts,
        )
        if d is not None:
            _add(session, subject_id, subject_type, snap.ts, d)
            last_alert = snap.ts
            count += 1
        history.append((snap.ts, price))
    return count


def rescan_spread(session, subject_id, subject_type, label, snap) -> int:
    """Spread alerts from the subject's latest snapshot (point-in-time)."""
    if snap is None:
        return 0
    n = 0
    if getattr(snap, "sources_json", None):
        d = detect_source_spread(
            label,
            json.loads(snap.sources_json),
            spread_threshold=settings.alert_spread_pct_threshold,
            now=snap.ts,
        )
        if d is not None:
            _add(session, subject_id, subject_type, snap.ts, d)
            n += 1
    cm_eur = getattr(snap, "cm_trend", None) or getattr(snap, "cm_avg_sell", None)
    if getattr(snap, "market", None):
        d = detect_regional_spread(
            label,
            snap.market,
            cm_eur,
            fx_rate=settings.eur_usd_rate,
            spread_threshold=settings.regional_spread_pct_threshold,
            now=snap.ts,
        )
        if d is not None:
            _add(session, subject_id, subject_type, snap.ts, d)
            n += 1
    return n


def main() -> None:
    init_db()
    with Session(engine) as session:
        existing = session.exec(select(Alert)).all()
        for a in existing:
            session.delete(a)
        session.commit()
        print(f"cleared {len(existing)} existing alerts")

    total = 0
    with Session(engine) as session:
        for card in session.exec(select(Card)).all():
            snaps = session.exec(
                select(PriceSnapshot)
                .where(PriceSnapshot.card_id == card.id)
                .order_by(PriceSnapshot.ts.asc())
            ).all()
            label = f"{card.name} ({card.set_name})"
            n = rescan(session, card.id, "card", label, snaps, lambda s: s.market)
            n += rescan_spread(
                session, card.id, "card", label, snaps[-1] if snaps else None
            )
            if n:
                print(f"  {card.name}: {n} alerts")
            total += n
        for product in session.exec(select(Product)).all():
            snaps = session.exec(
                select(ProductSnapshot)
                .where(ProductSnapshot.product_id == product.id)
                .order_by(ProductSnapshot.ts.asc())
            ).all()
            label = f"{product.name} ({product.set_name or 'sealed'})"
            n = rescan(session, product.id, "product", label, snaps, lambda s: s.price)
            n += rescan_spread(
                session, product.id, "product", label, snaps[-1] if snaps else None
            )
            if n:
                print(f"  {product.name}: {n} alerts")
            total += n
        session.commit()
    print(f"total: {total} alerts")


if __name__ == "__main__":
    main()
