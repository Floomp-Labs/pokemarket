from datetime import datetime, timedelta
from typing import Optional, Sequence


def pct_change(new: Optional[float], old: Optional[float]) -> Optional[float]:
    if new is None or old in (None, 0):
        return None
    return (new - old) / old * 100.0


def closest_at_or_before(snaps_desc: Sequence, target: datetime):
    """snaps_desc: snapshots sorted newest-first, each with a .ts attribute."""
    for snap in snaps_desc:
        if snap.ts <= target:
            return snap
    return snaps_desc[-1] if snaps_desc else None


def reference_at(snaps_desc: Sequence, target: datetime, tol: timedelta):
    """Closest snapshot at-or-before target, but only if it falls within
    [target - tol, target] — so a 7d-old anchor is never misread as a 24h change."""
    snap = closest_at_or_before(snaps_desc, target)
    if snap is None or snap.ts < target - tol:
        return None
    return snap
