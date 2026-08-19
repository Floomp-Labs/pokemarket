from datetime import datetime, timedelta

from app.agent.detector import detect_anomaly

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
