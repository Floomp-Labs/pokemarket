from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from ..db import get_session
from ..models import Alert, Card, Product

router = APIRouter(prefix="/api/alerts", tags=["alerts"])


@router.get("")
def list_alerts(limit: int = 50, session: Session = Depends(get_session)):
    rows = session.exec(select(Alert).order_by(Alert.ts.desc()).limit(limit)).all()

    card_ids = {a.subject_id for a in rows if a.subject_type == "card"}
    product_ids = {a.subject_id for a in rows if a.subject_type == "product"}
    cards = (
        {c.id: c for c in session.exec(select(Card).where(Card.id.in_(card_ids))).all()}
        if card_ids
        else {}
    )
    products = (
        {p.id: p for p in session.exec(select(Product).where(Product.id.in_(product_ids))).all()}
        if product_ids
        else {}
    )

    out = []
    for a in rows:
        name, image = a.subject_id, None
        if a.subject_type == "card" and a.subject_id in cards:
            name, image = cards[a.subject_id].name, cards[a.subject_id].image_small
        elif a.subject_type == "product" and a.subject_id in products:
            name, image = products[a.subject_id].name, products[a.subject_id].image_small
        out.append(
            {
                "id": a.id,
                "subject_id": a.subject_id,
                "subject_type": a.subject_type,
                "name": name,
                "image_small": image,
                "ts": a.ts.isoformat(),
                "kind": a.kind,
                "severity": a.severity,
                "pct_change": a.pct_change,
                "z_score": a.z_score,
                "message": a.message,
                "acknowledged": a.acknowledged,
            }
        )
    return out


@router.post("/{alert_id}/ack")
def ack_alert(alert_id: int, session: Session = Depends(get_session)):
    alert = session.get(Alert, alert_id)
    if alert is None:
        raise HTTPException(404, "alert not found")
    alert.acknowledged = True
    session.add(alert)
    session.commit()
    return {"ok": True}
