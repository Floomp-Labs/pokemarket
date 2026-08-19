import asyncio
import json
import logging
from datetime import timedelta
from typing import Optional

import httpx
from sqlmodel import Session, select

from .agent.detector import detect_anomaly
from .config import settings
from .db import engine
from .models import (
    Alert,
    Card,
    GradeSnapshot,
    PriceSnapshot,
    Product,
    ProductSnapshot,
    utcnow,
)
from .pricecharting_client import PriceChartingClient
from .service import backfill_card_anchors, compile_sources, match_card_pc_url
from .tcg_client import TCGClient, pick_price_type
from .tcgcsv_client import TCGCSVClient
from .tcgdex_client import TCGdexClient
from .ws import manager

log = logging.getLogger(__name__)


def _extract_snapshot_fields(card_data: dict, price_type: Optional[str]) -> Optional[dict]:
    tcg = card_data.get("tcgplayer") or {}
    prices = tcg.get("prices") or {}
    pt = price_type if price_type in prices else pick_price_type(prices)
    if not pt:
        return None
    block = prices[pt]
    cm = (card_data.get("cardmarket") or {}).get("prices") or {}
    return {
        "price_type": pt,
        "low": block.get("low"),
        "mid": block.get("mid"),
        "high": block.get("high"),
        "market": block.get("market"),
        "direct_low": block.get("directLow"),
        "source_updated_at": tcg.get("updatedAt"),
        "cm_avg1": cm.get("avg1"),
        "cm_avg7": cm.get("avg7"),
        "cm_avg30": cm.get("avg30"),
        "cm_trend": cm.get("trendPrice"),
        "cm_avg_sell": cm.get("averageSellPrice"),
        "cm_low": cm.get("lowPrice"),
        "variants": prices,
    }


def _last_alert_ts(session: Session, subject_id: str, subject_type: str):
    return session.exec(
        select(Alert.ts)
        .where(Alert.subject_id == subject_id)
        .where(Alert.subject_type == subject_type)
        .order_by(Alert.ts.desc())
        .limit(1)
    ).first()


def _build_alert(subject_id: str, subject_type: str, now, detection) -> Alert:
    return Alert(
        subject_id=subject_id,
        subject_type=subject_type,
        ts=now,
        kind=detection.kind,
        severity=detection.severity,
        pct_change=detection.pct_change,
        z_score=detection.z_score,
        message=detection.message,
    )


async def collect_card(
    tcg: TCGClient, csv: TCGCSVClient, dex: TCGdexClient, card_id: str
) -> None:
    # pokemontcg.io is one source among several now; tolerate it being down.
    data = None
    try:
        data = await tcg.get_card(card_id)
    except httpx.HTTPError:
        log.warning("pokemontcg unavailable for %s; using other sources", card_id)

    with Session(engine) as session:
        card = session.get(Card, card_id)
        if card is None:
            return
        price_type = card.price_type
        name, number, set_name = card.name, card.number, card.set_name
        csv_gid, csv_pid = card.tcgcsv_group_id, card.tcgcsv_product_id
        csv_attempted = card.tcgcsv_match_attempted
        dex_id, dex_attempted = card.tcgdex_id, card.tcgdex_match_attempted

    sources: dict[str, dict] = {}
    fields = _extract_snapshot_fields(data, price_type) if data else None
    if fields is not None and fields["market"] is not None:
        sources["pokemontcg"] = {
            k: fields[k] for k in ("market", "low", "mid", "high", "direct_low")
        }
        price_type = fields["price_type"]

    if csv_pid is None and not csv_attempted:
        try:
            csv_gid, csv_pid = await csv.resolve_card(name, number, set_name)
        except httpx.HTTPError:
            # Transient failure: leave attempted=False so we retry next cycle.
            log.warning("tcgcsv resolve failed for %s", card_id)
        else:
            with Session(engine) as session:
                card = session.get(Card, card_id)
                if card is None:
                    return
                card.tcgcsv_match_attempted = True
                card.tcgcsv_group_id = csv_gid
                card.tcgcsv_product_id = csv_pid
                session.add(card)
                session.commit()
            log.info(
                "tcgcsv match for %s: group=%s product=%s", card_id, csv_gid, csv_pid
            )
    if csv_gid is not None and csv_pid is not None:
        try:
            row = await csv.price_for(csv_gid, csv_pid, price_type)
            if row:
                sources["tcgcsv"] = row
        except httpx.HTTPError:
            log.warning("tcgcsv prices unavailable for %s", card_id)

    cm_fallback = None
    if dex_id is None and not dex_attempted:
        try:
            dex_id = await dex.match_card(name, number, set_name)
        except httpx.HTTPError:
            log.warning("tcgdex resolve failed for %s", card_id)
        else:
            with Session(engine) as session:
                card = session.get(Card, card_id)
                if card is None:
                    return
                card.tcgdex_match_attempted = True
                card.tcgdex_id = dex_id
                session.add(card)
                session.commit()
            log.info("tcgdex match for %s: %s", card_id, dex_id or "none found")
    if dex_id:
        try:
            usd, cm_fallback = await dex.price_for(dex_id, price_type)
            if usd:
                sources["tcgdex"] = usd
        except httpx.HTTPError:
            log.warning("tcgdex unavailable for %s", card_id)

    compiled = compile_sources(sources)
    market = compiled.get("market")
    if market is None:
        log.info("no price data for %s from any source", card_id)
        return

    now = utcnow()
    with Session(engine) as session:
        card = session.get(Card, card_id)
        if card is None:
            return

        # One-time 30-day backfill from Cardmarket trend averages.
        has_est = session.exec(
            select(PriceSnapshot.id)
            .where(PriceSnapshot.card_id == card_id)
            .where(PriceSnapshot.estimated == True)  # noqa: E712
            .limit(1)
        ).first()
        if has_est is None and data is not None:
            cm = (data.get("cardmarket") or {}).get("prices") or {}
            tcg_prices = (data.get("tcgplayer") or {}).get("prices") or {}
            added = backfill_card_anchors(
                session, card_id, market, cm, tcg_prices, now=now
            )
            if added:
                session.commit()
                log.info("backfilled %d estimated anchors for %s", added, card_id)

        last = session.exec(
            select(PriceSnapshot)
            .where(PriceSnapshot.card_id == card_id)
            .order_by(PriceSnapshot.ts.desc())
            .limit(1)
        ).first()
        if (
            last is not None
            and last.market == market
            and now - last.ts < timedelta(hours=settings.stale_snapshot_hours)
        ):
            return  # unchanged price; keep the series clean

        history = [
            (ts, m)
            for ts, m in session.exec(
                select(PriceSnapshot.ts, PriceSnapshot.market)
                .where(PriceSnapshot.card_id == card_id)
                .where(PriceSnapshot.market.is_not(None))
                .order_by(PriceSnapshot.ts.asc())
            ).all()
        ]
        last_alert = _last_alert_ts(session, card_id, "card")

        if price_type != card.price_type:
            card.price_type = price_type
            session.add(card)

        cm_fields = (
            {
                k: fields[k]
                for k in ("cm_avg1", "cm_avg7", "cm_avg30", "cm_trend", "cm_avg_sell", "cm_low")
            }
            if fields is not None
            else (cm_fallback or {})
        )

        session.add(
            PriceSnapshot(
                card_id=card_id,
                ts=now,
                low=compiled.get("low"),
                mid=compiled.get("mid"),
                high=compiled.get("high"),
                market=market,
                direct_low=compiled.get("direct_low"),
                source_updated_at=fields["source_updated_at"] if fields else None,
                variants_json=(
                    json.dumps(fields["variants"])
                    if fields is not None and fields["variants"]
                    else None
                ),
                sources_json=json.dumps(sources),
                **cm_fields,
            )
        )

        detection = detect_anomaly(
            f"{card.name} ({card.set_name})",
            history,
            market,
            pct_threshold=settings.alert_pct_threshold,
            z_threshold=settings.alert_z_threshold,
            cooldown_minutes=settings.alert_cooldown_minutes,
            last_alert_ts=last_alert,
            now=now,
        )
        alert = None
        if detection is not None:
            alert = _build_alert(card_id, "card", now, detection)
            session.add(alert)
            log.info("ALERT %s", detection.message)

        # ORM instances expire on commit; capture broadcast fields beforehand.
        price_type = card.price_type
        card_name = card.name
        card_image = card.image_small
        session.commit()
        alert_payload = None
        if alert is not None:
            session.refresh(alert)
            alert_payload = {
                "id": alert.id,
                "subject_id": card_id,
                "subject_type": "card",
                "name": card_name,
                "image_small": card_image,
                "ts": alert.ts.isoformat(),
                "kind": alert.kind,
                "severity": alert.severity,
                "pct_change": alert.pct_change,
                "z_score": alert.z_score,
                "message": alert.message,
                "acknowledged": False,
            }

    await manager.broadcast(
        {
            "type": "price_tick",
            "card_id": card_id,
            "ts": now.isoformat(),
            "market": market,
            "low": compiled.get("low"),
            "mid": compiled.get("mid"),
            "high": compiled.get("high"),
            "price_type": price_type,
        }
    )
    if alert_payload is not None:
        await manager.broadcast({"type": "alert", "alert": alert_payload})


async def collect_product(
    pc: PriceChartingClient, csv: TCGCSVClient, product_id: str
) -> None:
    with Session(engine) as session:
        product = session.get(Product, product_id)
        if product is None:
            return
        url, kind = product.url, product.price_kind
        name, image, set_name = product.name, product.image_small, product.set_name
        csv_gid, csv_pid = product.tcgcsv_group_id, product.tcgcsv_product_id
        csv_attempted = product.tcgcsv_match_attempted

    sources: dict[str, dict] = {}
    try:
        pc_price = await pc.get_current_price(url, kind)
        if pc_price is not None:
            sources["pricecharting"] = {"market": pc_price}
    except httpx.HTTPError:
        log.warning("pricecharting unavailable for product %s", product_id)

    if csv_pid is None and not csv_attempted:
        try:
            csv_gid, csv_pid = await csv.resolve_sealed(name, set_name)
        except httpx.HTTPError:
            log.warning("tcgcsv resolve failed for product %s", product_id)
        else:
            with Session(engine) as session:
                product = session.get(Product, product_id)
                if product is None:
                    return
                product.tcgcsv_match_attempted = True
                product.tcgcsv_group_id = csv_gid
                product.tcgcsv_product_id = csv_pid
                session.add(product)
                session.commit()
            log.info(
                "tcgcsv match for product %s: group=%s product=%s",
                product_id,
                csv_gid,
                csv_pid,
            )
    if csv_gid is not None and csv_pid is not None:
        try:
            row = await csv.price_for(csv_gid, csv_pid)
            if row:
                sources["tcgcsv"] = row
        except httpx.HTTPError:
            log.warning("tcgcsv unavailable for product %s", product_id)

    compiled = compile_sources(sources)
    market = compiled.get("market")
    if market is None:
        log.info("no price data for product %s from any source", product_id)
        return
    price = round(market, 2)

    with Session(engine) as session:
        now = utcnow()
        last = session.exec(
            select(ProductSnapshot)
            .where(ProductSnapshot.product_id == product_id)
            .order_by(ProductSnapshot.ts.desc())
            .limit(1)
        ).first()
        if (
            last is not None
            and last.price == price
            and now - last.ts < timedelta(hours=settings.stale_snapshot_hours)
        ):
            return

        history = [
            (ts, p)
            for ts, p in session.exec(
                select(ProductSnapshot.ts, ProductSnapshot.price)
                .where(ProductSnapshot.product_id == product_id)
                .order_by(ProductSnapshot.ts.asc())
            ).all()
        ]
        last_alert = _last_alert_ts(session, product_id, "product")

        session.add(
            ProductSnapshot(
                product_id=product_id,
                ts=now,
                price=price,
                sources_json=json.dumps(sources),
            )
        )

        detection = detect_anomaly(
            f"{name} ({set_name or 'sealed'})",
            history,
            price,
            pct_threshold=settings.alert_pct_threshold,
            z_threshold=settings.alert_z_threshold,
            cooldown_minutes=settings.alert_cooldown_minutes,
            last_alert_ts=last_alert,
            now=now,
        )
        alert = None
        if detection is not None:
            alert = _build_alert(product_id, "product", now, detection)
            session.add(alert)
            log.info("ALERT %s", detection.message)

        session.commit()
        alert_payload = None
        if alert is not None:
            session.refresh(alert)
            alert_payload = {
                "id": alert.id,
                "subject_id": product_id,
                "subject_type": "product",
                "name": name,
                "image_small": image,
                "ts": alert.ts.isoformat(),
                "kind": alert.kind,
                "severity": alert.severity,
                "pct_change": alert.pct_change,
                "z_score": alert.z_score,
                "message": alert.message,
                "acknowledged": False,
            }

    await manager.broadcast(
        {
            "type": "product_tick",
            "product_id": product_id,
            "ts": now.isoformat(),
            "price": price,
            "price_kind": kind,
        }
    )
    if alert_payload is not None:
        await manager.broadcast({"type": "alert", "alert": alert_payload})


async def collect_card_grades(pc: PriceChartingClient, card_id: str) -> None:
    """Resolve the card's PriceCharting page (once), then snapshot its PSA
    1-10 price guide whenever it changes. Refreshed at most once per
    stale_snapshot_hours; PC guide values update roughly daily."""
    with Session(engine) as session:
        card = session.get(Card, card_id)
        if card is None:
            return
        url, attempted = card.pc_url, card.pc_match_attempted
        name, number, set_name = card.name, card.number, card.set_name
        image = card.image_small

    if url is None:
        if attempted:
            return
        url = await match_card_pc_url(pc, name, number, set_name)
        with Session(engine) as session:
            card = session.get(Card, card_id)
            if card is None:
                return
            card.pc_match_attempted = True
            card.pc_url = url
            session.add(card)
            session.commit()
        log.info(
            "pricecharting match for %s: %s", card_id, url or "none found"
        )
        if url is None:
            return

    with Session(engine) as session:
        last = session.exec(
            select(GradeSnapshot)
            .where(GradeSnapshot.card_id == card_id)
            .order_by(GradeSnapshot.ts.desc())
            .limit(1)
        ).first()
        if last is not None and utcnow() - last.ts < timedelta(
            hours=settings.stale_snapshot_hours
        ):
            return
        last_json = last.prices_json if last else None

    prices = await pc.get_grade_prices(url)
    if not prices:
        log.info("no grade prices at %s", url)
        return
    payload = json.dumps(prices, sort_keys=True)
    if payload == last_json:
        return

    prev = json.loads(last_json) if last_json else None
    now = utcnow()
    alert_payload = None
    with Session(engine) as session:
        session.add(GradeSnapshot(card_id=card_id, ts=now, prices_json=payload))

        # Graded-price anomaly: biggest per-grade move vs the prior ladder.
        if prev:
            moves = [
                ((new - old) / old * 100.0, grade, old, new)
                for grade, new in prices.items()
                if (old := prev.get(grade))
            ]
            if moves:
                pct, grade, old, new = max(moves, key=lambda m: abs(m[0]))
                last_alert = _last_alert_ts(session, card_id, "card")
                cooled = last_alert is None or now - last_alert >= timedelta(
                    minutes=settings.alert_cooldown_minutes
                )
                if abs(pct) >= settings.grade_alert_pct_threshold and cooled:
                    glabel = {"ungraded": "Raw", "10": "PSA 10"}.get(
                        grade, f"PSA {grade}"
                    )
                    alert = Alert(
                        subject_id=card_id,
                        subject_type="card",
                        ts=now,
                        kind="grade_spike" if pct > 0 else "grade_drop",
                        severity=(
                            "critical"
                            if abs(pct) >= 2 * settings.grade_alert_pct_threshold
                            else "warn"
                        ),
                        pct_change=round(pct, 2),
                        message=(
                            f"{name} ({set_name}) graded "
                            f"{'spike' if pct > 0 else 'drop'}: {glabel} "
                            f"${old:,.2f} -> ${new:,.2f} ({pct:+.1f}%)"
                        ),
                    )
                    session.add(alert)
                    log.info("ALERT %s", alert.message)
                    session.commit()
                    session.refresh(alert)
                    alert_payload = {
                        "id": alert.id,
                        "subject_id": card_id,
                        "subject_type": "card",
                        "name": name,
                        "image_small": image,
                        "ts": alert.ts.isoformat(),
                        "kind": alert.kind,
                        "severity": alert.severity,
                        "pct_change": alert.pct_change,
                        "z_score": None,
                        "message": alert.message,
                        "acknowledged": False,
                    }
        if alert_payload is None:
            session.commit()
    log.info("grade snapshot for %s: %d prices", card_id, len(prices))
    if alert_payload is not None:
        await manager.broadcast({"type": "alert", "alert": alert_payload})


async def collect_all(
    tcg: TCGClient, pc: PriceChartingClient, csv: TCGCSVClient, dex: TCGdexClient
) -> None:
    with Session(engine) as session:
        card_ids = list(session.exec(select(Card.id)).all())
        product_ids = list(session.exec(select(Product.id)).all())

    sem = asyncio.Semaphore(4)

    async def one_card(cid: str) -> None:
        async with sem:
            try:
                await collect_card(tcg, csv, dex, cid)
            except Exception:
                log.exception("collect failed for card %s", cid)

    # Staggered batches to stay polite on the free tier's rate limit.
    for i in range(0, len(card_ids), 4):
        await asyncio.gather(*(one_card(cid) for cid in card_ids[i : i + 4]))
        await asyncio.sleep(1.0)

    for pid in product_ids:
        try:
            await collect_product(pc, csv, pid)
        except Exception:
            log.exception("collect failed for product %s", pid)
        await asyncio.sleep(0.5)

    for cid in card_ids:
        try:
            await collect_card_grades(pc, cid)
        except Exception:
            log.exception("grades collect failed for card %s", cid)
        await asyncio.sleep(0.5)


async def run_collector() -> None:
    tcg = TCGClient()
    pc = PriceChartingClient()
    csv = TCGCSVClient()
    dex = TCGdexClient()
    log.info("collector started, poll interval %ds", settings.poll_interval_seconds)
    try:
        while True:
            await collect_all(tcg, pc, csv, dex)
            await asyncio.sleep(settings.poll_interval_seconds)
    finally:
        await tcg.close()
        await pc.close()
        await csv.close()
        await dex.close()
