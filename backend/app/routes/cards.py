import json
from datetime import datetime, timedelta

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from ..db import get_session
from ..models import Alert, Card, GradeSnapshot, PriceSnapshot, utcnow
from ..service import add_card_from_api
from ..tcg_client import TCGClient, pick_price_type
from .util import pct_change, reference_at

router = APIRouter(prefix="/api/cards", tags=["cards"])


class AddCardRequest(BaseModel):
    id: str


@router.get("/search")
async def search(q: str):
    client = TCGClient()
    try:
        results = await client.search_cards(f"name:*{q}*")
    except httpx.HTTPError:
        raise HTTPException(502, "upstream price API unavailable, try again")
    finally:
        await client.close()
    out = []
    for c in results:
        prices = (c.get("tcgplayer") or {}).get("prices") or {}
        pt = pick_price_type(prices)
        out.append(
            {
                "id": c["id"],
                "name": c["name"],
                "set_id": c["set"]["id"],
                "set_name": c["set"]["name"],
                "number": c["number"],
                "rarity": c.get("rarity"),
                "image_small": (c.get("images") or {}).get("small"),
                "price_type": pt,
                "market": (prices.get(pt) or {}).get("market") if pt else None,
            }
        )
    return out


@router.get("")
def list_cards(session: Session = Depends(get_session)):
    cards = session.exec(select(Card).order_by(Card.added_at.asc())).all()
    now = utcnow()
    out = []
    for card in cards:
        snaps = session.exec(
            select(PriceSnapshot)
            .where(PriceSnapshot.card_id == card.id)
            .order_by(PriceSnapshot.ts.desc())
            .limit(200)
        ).all()
        latest = snaps[0] if snaps else None
        ref_24h = reference_at(snaps, now - timedelta(hours=24), timedelta(hours=24))
        ref_7d = reference_at(snaps, now - timedelta(days=7), timedelta(hours=48))
        active_alert = session.exec(
            select(Alert.id)
            .where(Alert.subject_id == card.id)
            .where(Alert.subject_type == "card")
            .where(Alert.acknowledged == False)  # noqa: E712
            .where(Alert.ts >= now - timedelta(hours=24))
            .limit(1)
        ).first()
        out.append(
            {
                "id": card.id,
                "name": card.name,
                "set_id": card.set_id,
                "set_name": card.set_name,
                "number": card.number,
                "rarity": card.rarity,
                "image_small": card.image_small,
                "price_type": card.price_type,
                "latest_market": latest.market if latest else None,
                "latest_ts": latest.ts.isoformat() if latest else None,
                "change_24h": pct_change(latest.market if latest else None, ref_24h.market if ref_24h else None),
                "change_7d": pct_change(latest.market if latest else None, ref_7d.market if ref_7d else None),
                "sparkline": [s.market for s in reversed(snaps[:48]) if s.market is not None],
                "active_alert": active_alert is not None,
            }
        )
    return out


@router.post("", status_code=201)
async def add_card(body: AddCardRequest, session: Session = Depends(get_session)):
    if session.get(Card, body.id):
        raise HTTPException(409, "card already tracked")
    client = TCGClient()
    try:
        card = await add_card_from_api(client, session, body.id)
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            raise HTTPException(404, "card not found on pokemontcg.io")
        raise HTTPException(502, "upstream price API unavailable, try again")
    except httpx.HTTPError:
        raise HTTPException(502, "upstream price API unavailable, try again")
    finally:
        await client.close()
    return {"ok": True, "id": card.id}


@router.delete("/{card_id}")
def remove_card(card_id: str, session: Session = Depends(get_session)):
    card = session.get(Card, card_id)
    if card is None:
        raise HTTPException(404, "card not tracked")
    for snap in session.exec(select(PriceSnapshot).where(PriceSnapshot.card_id == card_id)).all():
        session.delete(snap)
    for snap in session.exec(
        select(GradeSnapshot).where(GradeSnapshot.card_id == card_id)
    ).all():
        session.delete(snap)
    for alert in session.exec(
        select(Alert).where(Alert.subject_id == card_id).where(Alert.subject_type == "card")
    ).all():
        session.delete(alert)
    session.delete(card)
    session.commit()
    return {"ok": True}


@router.get("/{card_id}/history")
def history(card_id: str, days: int = 30, session: Session = Depends(get_session)):
    card = session.get(Card, card_id)
    if card is None:
        raise HTTPException(404, "card not tracked")
    since = datetime.min if days <= 0 else utcnow() - timedelta(days=days)
    rows = session.exec(
        select(PriceSnapshot)
        .where(PriceSnapshot.card_id == card_id)
        .where(PriceSnapshot.ts >= since)
        .order_by(PriceSnapshot.ts.asc())
    ).all()
    alerts = session.exec(
        select(Alert)
        .where(Alert.subject_id == card_id)
        .where(Alert.subject_type == "card")
        .where(Alert.ts >= since)
        .order_by(Alert.ts.asc())
    ).all()
    latest = rows[-1] if rows else None
    grade_snap = session.exec(
        select(GradeSnapshot)
        .where(GradeSnapshot.card_id == card_id)
        .order_by(GradeSnapshot.ts.desc())
        .limit(1)
    ).first()
    return {
        "psa": (
            {
                "ts": grade_snap.ts.isoformat(),
                "url": card.pc_url,
                "prices": json.loads(grade_snap.prices_json),
            }
            if grade_snap
            else None
        ),
        "card": {
            "id": card.id,
            "name": card.name,
            "set_id": card.set_id,
            "set_name": card.set_name,
            "number": card.number,
            "rarity": card.rarity,
            "image_small": card.image_small,
            "image_large": card.image_large,
            "price_type": card.price_type,
            "latest_market": latest.market if latest else None,
            "latest_ts": latest.ts.isoformat() if latest else None,
        },
        "sources": (
            json.loads(latest.sources_json)
            if latest is not None and latest.sources_json
            else None
        ),
        "points": [
            {
                "ts": r.ts.isoformat(),
                "low": r.low,
                "mid": r.mid,
                "high": r.high,
                "market": r.market,
                "direct_low": r.direct_low,
                "estimated": r.estimated,
                "cm_avg1": r.cm_avg1,
                "cm_avg7": r.cm_avg7,
                "cm_avg30": r.cm_avg30,
                "cm_trend": r.cm_trend,
                "cm_avg_sell": r.cm_avg_sell,
                "cm_low": r.cm_low,
                "variants": json.loads(r.variants_json) if r.variants_json else None,
            }
            for r in rows
        ],
        "alerts": [
            {
                "id": a.id,
                "ts": a.ts.isoformat(),
                "kind": a.kind,
                "severity": a.severity,
                "pct_change": a.pct_change,
                "z_score": a.z_score,
                "message": a.message,
            }
            for a in alerts
        ],
    }
