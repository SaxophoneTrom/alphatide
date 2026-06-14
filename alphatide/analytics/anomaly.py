"""On-chain anomaly detection (secondary signal).

A lightweight statistical baseline that flags abnormal per-token transfer volume
in the scan window. Complements the primary cross-chain smart money detector:
"smart money moved" + "volume is anomalous" = a higher-conviction alert.
"""

from __future__ import annotations

import statistics
from collections import defaultdict

from alphatide.core.models import TransferEvent


def volume_zscores(
    events: list[TransferEvent], history: dict[str, list[float]]
) -> dict[str, float]:
    """Z-score of each token's current window USD volume vs its history.

    `history` maps token symbol → list of prior windows' total USD volume.
    Returns token → z-score (0 when history is too short to judge).
    """
    current: dict[str, float] = defaultdict(float)
    for ev in events:
        current[ev.token_symbol] += ev.amount_usd

    out: dict[str, float] = {}
    for sym, vol in current.items():
        past = history.get(sym, [])
        if len(past) < 5:
            out[sym] = 0.0
            continue
        mu = statistics.mean(past)
        sigma = statistics.pstdev(past) or 1.0
        out[sym] = round((vol - mu) / sigma, 2)
    return out


def is_anomalous(zscore: float, threshold: float = 3.0) -> bool:
    return abs(zscore) >= threshold
