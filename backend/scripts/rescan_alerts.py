"""Replay stored snapshots through the anomaly detector with the current
thresholds, rebuilding the alerts table: python -m scripts.rescan_alerts

Existing alerts are wiped so the feed reflects exactly what the detector
fires on the recorded history (no duplicates vs. live collection).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlmodel import Session, select

from app.agent.detector import detect_anomaly
from app.config import settings
from app.db import engine, init_db
from app.models import Alert, Card, PriceSnapshot, Product, ProductSnapshot


def rescan(subject_id: str, subject_type: str, label: str, snaps, price_of) -> int:
    history: list = []
    last_alert = None
    count = 0
    with Session(engine) as session:
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
                session.add(
                    Alert(
                        subject_id=subject_id,
                        subject_type=subject_type,
                        ts=snap.ts,
                        kind=d.kind,
                        severity=d.severity,
                        pct_change=d.pct_change,
                        z_score=d.z_score,
                        message=d.message,
                    )
                )
                last_alert = snap.ts
                count += 1
            history.append((snap.ts, price))
        session.commit()
    return count


def main() -> None:
    init_db()
    with Session(engine) as session:
        existing = session.exec(select(Alert)).all()
        for a in existing:
            session.delete(a)
        session.commit()
        print(f"cleared {len(existing)} existing alerts")

        cards = session.exec(select(Card)).all()
        products = session.exec(select(Product)).all()

    total = 0
    with Session(engine) as session:
        for card in cards:
            snaps = session.exec(
                select(PriceSnapshot)
                .where(PriceSnapshot.card_id == card.id)
                .order_by(PriceSnapshot.ts.asc())
            ).all()
            n = rescan(
                card.id,
                "card",
                f"{card.name} ({card.set_name})",
                snaps,
                lambda s: s.market,
            )
            if n:
                print(f"  {card.name}: {n} alerts")
            total += n
        for product in products:
            snaps = session.exec(
                select(ProductSnapshot)
                .where(ProductSnapshot.product_id == product.id)
                .order_by(ProductSnapshot.ts.asc())
            ).all()
            n = rescan(
                product.id,
                "product",
                f"{product.name} ({product.set_name or 'sealed'})",
                snaps,
                lambda s: s.price,
            )
            if n:
                print(f"  {product.name}: {n} alerts")
            total += n
    print(f"total: {total} alerts")


if __name__ == "__main__":
    main()
