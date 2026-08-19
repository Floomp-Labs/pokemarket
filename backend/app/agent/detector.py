"""Anomaly detection over per-card price history. Pure functions, no I/O."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from statistics import mean, pstdev
from typing import Mapping, Optional, Sequence

SOURCE_NAMES = {
    "pokemontcg": "TCGplayer",
    "tcgcsv": "TCGCSV",
    "tcgdex": "TCGdex",
    "pricecharting": "PriceCharting",
}


@dataclass
class Detection:
    kind: str  # spike | drop | trend_reversal
    severity: str  # warn | critical
    pct_change: float
    z_score: Optional[float]
    message: str


def _pct(new: float, old: float) -> float:
    if old == 0:
        return 0.0
    return (new - old) / old * 100.0


def detect_anomaly(
    card_label: str,
    history: Sequence[tuple[datetime, float]],
    new_price: float,
    *,
    pct_threshold: float = 10.0,
    z_threshold: float = 2.5,
    cooldown_minutes: int = 60,
    last_alert_ts: Optional[datetime] = None,
    now: Optional[datetime] = None,
) -> Optional[Detection]:
    """Inspect a new market price against prior (ts, price) history.

    Triggers when the move breaches the pct-change or z-score threshold, or
    flips the prevailing short-term trend with enough magnitude. A per-card
    cooldown suppresses repeat alerts. Returns None when nothing fires.
    """
    if not history:
        return None
    now = now or history[-1][0]

    if last_alert_ts is not None and now - last_alert_ts < timedelta(minutes=cooldown_minutes):
        return None

    prev_price = history[-1][1]
    pct_prev = _pct(new_price, prev_price)

    # Cumulative drift vs the point nearest 7 days ago. Day-over-day moves
    # are often tiny while the week trend is large; anchors make a 7d
    # reference available from day one.
    ref_7d = None
    target_7d = now - timedelta(days=7)
    for ts, p in history:
        if ts <= target_7d:
            ref_7d = (ts, p)
        else:
            break
    pct_7d = None
    if (
        ref_7d is not None
        and ref_7d[0] >= target_7d - timedelta(days=3)
        and ref_7d[1]
    ):
        pct_7d = _pct(new_price, ref_7d[1])

    recent = [p for ts, p in history if ts >= now - timedelta(days=30)]
    window = recent if recent else [p for _, p in history]
    mu = mean(window)
    sigma = pstdev(window) if len(window) > 1 else 0.0
    z = (new_price - mu) / sigma if sigma > 0 else None

    reversal = False
    short = [p for _, p in history[-3:]]
    long_ = [p for _, p in history[-13:-3]]
    if len(short) == 3 and len(long_) >= 3:
        short_mu = mean(short)
        trend_dir = short_mu - mean(long_)
        move_dir = new_price - short_mu
        if trend_dir != 0 and move_dir != 0 and (trend_dir > 0) != (move_dir > 0):
            reversal = abs(_pct(new_price, short_mu)) >= pct_threshold / 2

    pct_hit = abs(pct_prev) >= pct_threshold
    # On near-flat series sigma approaches zero and any move becomes a huge
    # z-score; require a minimum absolute move so +0.0% "spikes" can't fire.
    z_min_pct = max(1.0, pct_threshold / 4)
    z_hit = (
        z is not None
        and abs(z) >= z_threshold
        and abs(pct_prev) >= z_min_pct
    )
    drift_hit = pct_7d is not None and abs(pct_7d) >= pct_threshold
    if not (pct_hit or z_hit or reversal or drift_hit):
        return None

    up = pct_prev > 0 or (
        pct_prev == 0 and ((z is not None and z > 0) or (pct_7d or 0) > 0)
    )
    if reversal and not (pct_hit or z_hit or drift_hit):
        kind = "trend_reversal"
    else:
        kind = "spike" if up else "drop"
    critical = (
        abs(pct_prev) >= 2 * pct_threshold
        or (z is not None and abs(z) >= 1.5 * z_threshold)
        or (pct_7d is not None and abs(pct_7d) >= 2 * pct_threshold)
    )

    message = (
        f"{card_label} {kind.replace('_', ' ')}: "
        f"market ${prev_price:.2f} -> ${new_price:.2f} ({pct_prev:+.1f}%)"
    )
    if pct_7d is not None and drift_hit:
        message += f", {pct_7d:+.1f}% vs 7d ago"
    if z is not None:
        message += f", z={z:+.2f} vs 30d mean ${mu:.2f}"

    return Detection(
        kind=kind,
        severity="critical" if critical else "warn",
        pct_change=pct_prev,
        z_score=z,
        message=message,
    )


def detect_source_spread(
    card_label: str,
    sources: Mapping[str, dict],
    *,
    spread_threshold: float = 8.0,
    cooldown_minutes: int = 720,
    last_alert_ts: Optional[datetime] = None,
    now: Optional[datetime] = None,
) -> Optional[Detection]:
    """Flag when price sources disagree on the current market price.

    Unlike detect_anomaly this needs no history: a wide gap between sources
    (e.g. TCGplayer $85 vs TCGCSV $97) is itself an anomaly — stale feeds,
    mispriced listings, or an arbitrage window. Fires on a single snapshot,
    which makes it the first signal available for newly tracked subjects.
    """
    vals = [
        (key, float(v["market"]))
        for key, v in sources.items()
        if v and v.get("market")
    ]
    if len(vals) < 2:
        return None

    now = now or datetime.now()
    if last_alert_ts is not None and now - last_alert_ts < timedelta(minutes=cooldown_minutes):
        return None

    lo = min(vals, key=lambda kv: kv[1])
    hi = max(vals, key=lambda kv: kv[1])
    if lo[1] <= 0:
        return None
    spread = (hi[1] - lo[1]) / lo[1] * 100.0
    if spread < spread_threshold:
        return None

    lo_name = SOURCE_NAMES.get(lo[0], lo[0])
    hi_name = SOURCE_NAMES.get(hi[0], hi[0])
    return Detection(
        kind="source_spread",
        severity="critical" if spread >= 2 * spread_threshold else "warn",
        pct_change=round(spread, 2),
        z_score=None,
        message=(
            f"{card_label} source spread: {lo_name} ${lo[1]:.2f} vs "
            f"{hi_name} ${hi[1]:.2f} ({spread:.1f}% gap)"
        ),
    )


def detect_regional_spread(
    card_label: str,
    usd_market: Optional[float],
    eur_price: Optional[float],
    *,
    fx_rate: float = 1.08,
    spread_threshold: float = 25.0,
    cooldown_minutes: int = 720,
    last_alert_ts: Optional[datetime] = None,
    now: Optional[datetime] = None,
) -> Optional[Detection]:
    """Flag exceptional US-vs-EU price gaps (Cardmarket EUR, FX-adjusted).

    EU prices sit structurally below US ones for modern English cards, so
    the threshold is deliberately high: this fires only on gaps wide enough
    to be actionable (e.g. buy EU / sell US), not on the usual discount.
    """
    if not usd_market or not eur_price or usd_market <= 0 or eur_price <= 0:
        return None

    now = now or datetime.now()
    if last_alert_ts is not None and now - last_alert_ts < timedelta(minutes=cooldown_minutes):
        return None

    eu_as_usd = eur_price * fx_rate
    lo, hi = min(usd_market, eu_as_usd), max(usd_market, eu_as_usd)
    gap = (hi - lo) / lo * 100.0
    if gap < spread_threshold:
        return None

    return Detection(
        kind="regional_spread",
        severity="critical" if gap >= 2 * spread_threshold else "warn",
        pct_change=round(gap, 2),
        z_score=None,
        message=(
            f"{card_label} regional spread: US ${usd_market:.2f} vs "
            f"EU ~${eu_as_usd:.2f} ({gap:.0f}% gap)"
        ),
    )
