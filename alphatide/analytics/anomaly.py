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
        min_volume_usd: float | None = None, min_ratio: float | None = None,
    ) -> None:
        self.threshold = threshold
        self.max_history = max_history
        self.min_volume_usd = (
            settings.anomaly_min_volume_usd if min_volume_usd is None else min_volume_usd
        )
        self.min_ratio = (
            settings.anomaly_min_ratio if min_ratio is None else min_ratio
        )

    @staticmethod
    def _contributors(ctx: DetectionContext, token: str, top: int = 3) -> list[dict]:
        """Actors driving a token's volume — excludes DEX pools / contracts.

        large_movers() aggregates both sides of each transfer, so the pool that
        every swap routes through would otherwise top the list. Skip labeled
        infrastructure (dex/contract/...) so we name actors, not the sink.
        """
        from alphatide.analytics.scoring import NON_ACTOR_TYPES

        out: list[dict] = []
        for addr, evs in ctx.movers.items():
            tok_usd = sum(e.amount_usd for e in evs if e.token_symbol == token)
            if tok_usd <= 0:
                continue
            lab = ctx.labels.get(addr)
            et = (lab.entity_type or "").lower() if lab else ""
            if et in NON_ACTOR_TYPES:  # DEX pool / token contract = routing sink
                continue
            who = lab.entity_name if (lab and lab.is_labeled) else None
            out.append({"who": who, "addr": addr, "usd": round(tok_usd)})
        out.sort(key=lambda c: -c["usd"])
        return out[:top]

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
            # Require an economically meaningful spike, not just a statistical one.
            if ratio < self.min_ratio:
                continue
            rtxt = f"{ratio:.1f}×" if ratio < 100 else "100×+"  # cap absurd display
            # Attribute the spike: who are the large movers in this token? Answers
            # the alert's own "check who's behind it" automatically.
            contributors = self._contributors(ctx, token)
            labeled = [c for c in contributors if c["who"]]
            score = round(min(80.0, 45.0 + 7.0 * (z - self.threshold + 1)), 1)
            alerts.append(
                Alert(
                    kind=AlertKind.ANOMALY,
                    score=score,
                    emoji="📈",
                    headline=f"{token} volume spike — {rtxt} baseline",
                    detail=(
                        f"{token} transfer volume this window is ~${vol:,.0f} vs a "
                        f"~${baseline:,.0f} baseline ({rtxt}, {z:.1f}σ)"
                        + (f" — driven partly by {labeled[0]['who']}."
                           if labeled else " — large movers look unlabeled/anonymous.")
                    ),
                    token=token,
                    extra={
                        "zscore": z, "volume_usd": vol, "ratio": round(ratio, 2),
                        "contributors": contributors,
                    },
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
