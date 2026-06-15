"""On-chain anomaly detection (idea I — secondary signal).

A lightweight statistical baseline that flags abnormal per-token transfer volume
in the scan window. Pure RPC math — **zero Surf credits**. Complements the
cross-chain detectors: it catches abnormal moves even when no labeled wallet is
involved, and "smart money moved + volume is anomalous" = higher conviction.
"""

from __future__ import annotations

import statistics
from collections import defaultdict

from alphatide.core.config import settings
from alphatide.core.models import Alert, AlertKind, DetectionContext, TransferEvent


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
        # Floor sigma relative to the mean so flat/low-variance history can't
        # produce absurd z-scores (div-by-~0). Clamp to a sane range.
        sigma = max(statistics.pstdev(past), 0.2 * abs(mu), 1.0)
        z = (vol - mu) / sigma
        out[sym] = round(max(-50.0, min(50.0, z)), 2)
    return out


def is_anomalous(zscore: float, threshold: float = 3.0) -> bool:
    return abs(zscore) >= threshold


def window_volumes(events: list[TransferEvent]) -> dict[str, float]:
    vol: dict[str, float] = defaultdict(float)
    for ev in events:
        vol[ev.token_symbol] += ev.amount_usd
    return dict(vol)


class VolumeAnomalyDetector:
    """Flags tokens whose current-window USD volume is a statistical outlier.

    Reads/writes `ctx.volume_history` (token -> past window totals) which the
    pipeline persists across cycles. Stays silent until it has enough history.
    """

    name = "anomaly"

    def __init__(
        self, threshold: float = 3.0, max_history: int = 50,
        min_volume_usd: float | None = None,
    ) -> None:
        self.threshold = threshold
        self.max_history = max_history
        self.min_volume_usd = (
            settings.anomaly_min_volume_usd if min_volume_usd is None else min_volume_usd
        )

    def detect_ctx(self, ctx: DetectionContext) -> list[Alert]:
        current = window_volumes(ctx.events)
        zs = volume_zscores(ctx.events, ctx.volume_history)
        alerts: list[Alert] = []
        for token, z in zs.items():
            # Spikes only — a volume *drop* is just quiet, not alpha. And ignore
            # spikes whose absolute volume is trivial (noise on a quiet chain).
            if z < self.threshold:
                continue
            vol = current.get(token, 0.0)
            if vol < self.min_volume_usd:
                continue
            baseline = statistics.mean(ctx.volume_history.get(token, [vol])) or 1.0
            ratio = vol / baseline
            # Anomaly is a *secondary* signal — capped below named smart-money so
            # labeled findings lead the digest. Value is in confluence.
            score = round(min(80.0, 45.0 + 7.0 * (z - self.threshold + 1)), 1)
            alerts.append(
                Alert(
                    kind=AlertKind.ANOMALY,
                    score=score,
                    emoji="📈",
                    headline=f"{token} volume spike — {ratio:.1f}× baseline",
                    detail=(
                        f"{token} transfer volume this window is ~${vol:,.0f} vs a "
                        f"~${baseline:,.0f} baseline ({ratio:.1f}×, {z:.1f}σ) — "
                        f"unusual activity; check who's behind it."
                    ),
                    token=token,
                    extra={"zscore": z, "volume_usd": vol, "ratio": round(ratio, 2)},
                )
            )
        # update rolling history AFTER scoring (so current isn't compared to itself)
        for token, vol in current.items():
            hist = ctx.volume_history.setdefault(token, [])
            hist.append(vol)
            if len(hist) > self.max_history:
                del hist[: len(hist) - self.max_history]
        alerts.sort(key=lambda a: a.score, reverse=True)
        return alerts
