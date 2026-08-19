"""Anomaly detection over per-card price history. Pure functions, no I/O."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from statistics import mean, pstdev
from typing import Optional, Sequence


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
    z_hit = z is not None and abs(z) >= z_threshold
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
