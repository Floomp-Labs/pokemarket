import json
from datetime import datetime, timedelta

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from ..db import get_session
from ..models import Alert, Product, ProductSnapshot, utcnow
from ..pricecharting_client import PriceChartingClient
from ..service import ProductMeta, add_product_from_meta
from .util import pct_change, reference_at

router = APIRouter(prefix="/api/products", tags=["products"])


@router.get("/search")
async def search(q: str):
    client = PriceChartingClient()
    try:
        results = await client.search_products(q)
    except httpx.HTTPError:
        raise HTTPException(502, "pricecharting unavailable, try again")
    finally:
        await client.close()
    out = []
    for r in results:
        kind = (
            "new"
            if r["new"] is not None
            else "cib"
            if r["cib"] is not None
            else "used"
            if r["used"] is not None
            else None
        )
        out.append({**r, "price_kind": kind, "price": r[kind] if kind else None})
    return out


class AddProductRequest(BaseModel):
    id: str
    name: str
    set_name: str | None = None
    url: str
    image_small: str | None = None
    used: float | None = None
    cib: float | None = None
    new: float | None = None


@router.post("", status_code=201)
async def add_product(body: AddProductRequest, session: Session = Depends(get_session)):
    if not body.url.startswith("https://www.pricecharting.com/"):
        raise HTTPException(400, "invalid pricecharting url")
    if session.get(Product, body.id):
        raise HTTPException(409, "product already tracked")
    client = PriceChartingClient()
    try:
        product = await add_product_from_meta(
            client, session, ProductMeta(**body.model_dump())
        )
    except httpx.HTTPError:
        raise HTTPException(502, "pricecharting unavailable, try again")
    finally:
        await client.close()
    return {"ok": True, "id": product.id}


@router.get("")
def list_products(session: Session = Depends(get_session)):
    products = session.exec(select(Product).order_by(Product.added_at.asc())).all()
    now = utcnow()
    out = []
    for p in products:
        snaps = session.exec(
            select(ProductSnapshot)
            .where(ProductSnapshot.product_id == p.id)
            .order_by(ProductSnapshot.ts.desc())
            .limit(200)
        ).all()
        latest = snaps[0] if snaps else None
        ref_24h = reference_at(snaps, now - timedelta(hours=24), timedelta(hours=24))
        # PriceCharting history is monthly, so the meaningful sealed-product
        # delta is month-over-month vs the previous point.
        ref_prev = snaps[1] if len(snaps) > 1 else None
        active_alert = session.exec(
            select(Alert.id)
            .where(Alert.subject_id == p.id)
            .where(Alert.subject_type == "product")
            .where(Alert.acknowledged == False)  # noqa: E712
            .where(Alert.ts >= now - timedelta(hours=24))
            .limit(1)
        ).first()
        out.append(
            {
                "id": p.id,
                "name": p.name,
                "set_name": p.set_name,
                "url": p.url,
                "image_small": p.image_small,
                "price_kind": p.price_kind,
                "latest_price": latest.price if latest else None,
                "latest_ts": latest.ts.isoformat() if latest else None,
                "change_24h": pct_change(latest.price if latest else None, ref_24h.price if ref_24h else None),
                "change_prev": pct_change(latest.price if latest else None, ref_prev.price if ref_prev else None),
                "sparkline": [s.price for s in reversed(snaps[:48])],
                "active_alert": active_alert is not None,
            }
        )
    return out


@router.delete("/{product_id}")
def remove_product(product_id: str, session: Session = Depends(get_session)):
    product = session.get(Product, product_id)
    if product is None:
        raise HTTPException(404, "product not tracked")
    for snap in session.exec(
        select(ProductSnapshot).where(ProductSnapshot.product_id == product_id)
    ).all():
        session.delete(snap)
    for alert in session.exec(
        select(Alert)
        .where(Alert.subject_id == product_id)
        .where(Alert.subject_type == "product")
    ).all():
        session.delete(alert)
    session.delete(product)
    session.commit()
    return {"ok": True}


@router.get("/{product_id}/history")
def product_history(product_id: str, days: int = 30, session: Session = Depends(get_session)):
    product = session.get(Product, product_id)
    if product is None:
        raise HTTPException(404, "product not tracked")
    since = datetime.min if days <= 0 else utcnow() - timedelta(days=days)
    rows = session.exec(
        select(ProductSnapshot)
        .where(ProductSnapshot.product_id == product_id)
        .where(ProductSnapshot.ts >= since)
        .order_by(ProductSnapshot.ts.asc())
    ).all()
    alerts = session.exec(
        select(Alert)
        .where(Alert.subject_id == product_id)
        .where(Alert.subject_type == "product")
        .where(Alert.ts >= since)
        .order_by(Alert.ts.asc())
    ).all()
    latest = rows[-1] if rows else None
    return {
        "product": {
            "id": product.id,
            "name": product.name,
            "set_name": product.set_name,
            "url": product.url,
            "image_small": product.image_small,
            "price_kind": product.price_kind,
            "latest_price": latest.price if latest else None,
            "latest_ts": latest.ts.isoformat() if latest else None,
        },
        "sources": (
            json.loads(latest.sources_json)
            if latest is not None and latest.sources_json
            else None
        ),
        "points": [
            {"ts": r.ts.isoformat(), "price": r.price, "estimated": r.estimated}
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
