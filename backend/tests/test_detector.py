from datetime import datetime, timedelta

from app.agent.detector import (
    detect_anomaly,
    detect_regional_spread,
    detect_source_spread,
)

BASE = datetime(2026, 8, 1, 12, 0, 0)


def make_history(prices, step_hours=6):
    return [(BASE + timedelta(hours=step_hours * i), p) for i, p in enumerate(prices)]


def after(history, steps=1):
    return history[-1][0] + timedelta(hours=6 * steps)


def test_stable_series_no_alert():
    h = make_history([100, 101, 99, 100, 100, 101])
    assert detect_anomaly("Test", h, 100.5, now=after(h)) is None


def test_spike_detected_as_critical():
    h = make_history([100, 100, 100, 100])
    d = detect_anomaly("Test", h, 125.0, now=after(h))
    assert d is not None
    assert d.kind == "spike"
    assert d.pct_change == 25.0
    assert d.severity == "critical"  # 25% >= 2x the 10% threshold


def test_drop_detected_as_warn():
    h = make_history([100, 100, 100, 100])
    d = detect_anomaly("Test", h, 85.0, now=after(h))
    assert d is not None
    assert d.kind == "drop"
    assert d.severity == "warn"


def test_cooldown_suppresses_repeat_alerts():
    h = make_history([100, 100, 100, 100])
    now = after(h)
    d = detect_anomaly(
        "Test", h, 130.0, last_alert_ts=now - timedelta(minutes=10), now=now
    )
    assert d is None


def test_cooldown_expired_allows_alert():
    h = make_history([100, 100, 100, 100])
    now = after(h)
    d = detect_anomaly(
        "Test", h, 130.0, last_alert_ts=now - timedelta(minutes=61), now=now
    )
    assert d is not None


def test_zscore_triggers_below_pct_threshold():
    # Extremely stable series: a 4% move is a massive z-score.
    h = make_history([100.0] * 20 + [100.1, 99.9, 100.05])
    d = detect_anomaly("Test", h, 104.0, now=after(h))
    assert d is not None
    assert d.z_score is not None and abs(d.z_score) >= 2.5


def test_trend_reversal():
    # Steady uptrend, then a move down that is small vs the previous point
    # but significant against the short-term mean.
    h = make_history([80, 85, 90, 95, 100, 105, 110, 115, 120, 125, 130, 140, 135, 139])
    d = detect_anomaly("Test", h, 126.0, now=after(h))
    assert d is not None
    assert d.kind == "trend_reversal"
    assert d.severity == "warn"


def test_empty_history_no_alert():
    assert detect_anomaly("Test", [], 100.0) is None


def test_zscore_spam_guard_suppresses_tiny_moves():
    # Flat series: sigma ~ 0 makes a +0.5% move a giant z-score, but a
    # sub-1% absolute move is noise, not signal.
    h = make_history([100.0] * 20)
    assert detect_anomaly("Test", h, 100.5, now=after(h)) is None


def test_source_spread_fires_on_wide_gap():
    sources = {
        "pokemontcg": {"market": 100.0},
        "tcgcsv": {"market": 120.0},
    }
    d = detect_source_spread("Test", sources, spread_threshold=8.0)
    assert d is not None
    assert d.kind == "source_spread"
    assert d.severity == "critical"  # 20% >= 2x the 8% threshold
    assert d.pct_change == 20.0


def test_source_spread_warn_severity():
    sources = {
        "tcgdex": {"market": 100.0},
        "pricecharting": {"market": 110.0},
    }
    d = detect_source_spread("Test", sources, spread_threshold=8.0)
    assert d is not None
    assert d.severity == "warn"


def test_source_spread_ignores_tight_sources():
    sources = {
        "pokemontcg": {"market": 100.0},
        "tcgcsv": {"market": 104.0},
        "tcgdex": {"market": 102.0},
    }
    assert detect_source_spread("Test", sources, spread_threshold=8.0) is None


def test_source_spread_needs_two_sources():
    assert (
        detect_source_spread("Test", {"pokemontcg": {"market": 100.0}}) is None
    )
    assert detect_source_spread("Test", {}) is None


def test_source_spread_cooldown():
    sources = {"a": {"market": 100.0}, "b": {"market": 130.0}}
    now = datetime(2026, 8, 19, 12, 0, 0)
    assert (
        detect_source_spread(
            "Test",
            sources,
            last_alert_ts=now - timedelta(hours=2),
            now=now,
        )
        is None
    )
    assert (
        detect_source_spread(
            "Test",
            sources,
            last_alert_ts=now - timedelta(hours=13),
            now=now,
        )
        is not None
    )


def test_regional_spread_fires_on_wide_gap():
    # US $100 vs EU EUR 50 (~$54 at 1.08) -> 85% gap, critical at 2x threshold.
    d = detect_regional_spread("Test", 100.0, 50.0, spread_threshold=25.0)
    assert d is not None
    assert d.kind == "regional_spread"
    assert d.severity == "critical"


def test_regional_spread_ignores_normal_discount():
    # US $40 vs EU EUR 33 (~$35.64) -> 12% gap, below the 25% bar.
    assert detect_regional_spread("Test", 40.0, 33.0, spread_threshold=25.0) is None


def test_regional_spread_requires_both_prices():
    assert detect_regional_spread("Test", None, 33.0) is None
    assert detect_regional_spread("Test", 40.0, None) is None
