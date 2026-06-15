"""End-to-end orchestration: scan Mantle once → run the detector suite.

One Mantle scan and one batched Surf label lookup feed every detector, so adding
detectors (B/C/I alongside 7-A) costs no extra credits. This is the single entry
point the bot, the monitor loop, and the demo all call.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from alphatide.analytics.action_read import attach_read
from alphatide.analytics.anomaly import VolumeAnomalyDetector
from alphatide.analytics.convergence import ConvergenceDetector
from alphatide.analytics.inflow import InflowDetector
from alphatide.analytics.smart_money import CrossChainSmartMoneyDetector
from alphatide.core.config import settings
from alphatide.core.models import Alert, DetectionContext, TransferEvent
from alphatide.data.mantle_client import MantleClient, large_movers
from alphatide.data.surf_client import SurfClient


@dataclass
class CycleResult:
    alerts: list[Alert]
    scanned_events: int
    candidates: int
    credits_used: int
    latest_block: int


class AlphaTidePipeline:
    def __init__(
        self,
        mantle: MantleClient | None = None,
        surf: SurfClient | None = None,
        detectors: list | None = None,
    ) -> None:
        self.mantle = mantle or MantleClient()
        self.surf = surf or SurfClient()
        self.detectors = detectors or [
            CrossChainSmartMoneyDetector(self.surf),  # 7-A
            ConvergenceDetector(),                    # B
            InflowDetector(),                         # C
            VolumeAnomalyDetector(),                  # I
        ]
        # rolling per-token volume history for the anomaly detector
        self.volume_history: dict[str, list[float]] = {}

    def build_context(
        self, window: int | None = None, min_usd: float | None = None
    ) -> tuple[DetectionContext, int]:
        min_usd = settings.min_candidate_usd if min_usd is None else min_usd
        latest = self.mantle.latest_block()
        events: list[TransferEvent] = self.mantle.scan_recent(window=window)
        movers = large_movers(events, min_usd)
        labels = self.surf.label_addresses(list(movers.keys())) if movers else {}
        ctx = DetectionContext(
            events=events,
            movers=movers,
            labels=labels,
            min_usd=min_usd,
            volume_history=self.volume_history,
            latest_block=latest,
        )
        return ctx, latest

    def run_cycle(
        self, window: int | None = None, min_usd: float | None = None
    ) -> CycleResult:
        before = self.surf.credits_used
        ctx, latest = self.build_context(window=window, min_usd=min_usd)

        alerts: list[Alert] = []
        for det in self.detectors:
            try:
                alerts.extend(det.detect_ctx(ctx))
            except Exception:
                continue  # one detector failing must not sink the cycle
        # attach the free, deterministic Action Read to every alert
        for a in alerts:
            try:
                attach_read(a)
            except Exception:
                pass
        alerts.sort(key=lambda a: a.score, reverse=True)

        return CycleResult(
            alerts=alerts,
            scanned_events=len(ctx.events),
            candidates=len(ctx.movers),
            credits_used=self.surf.credits_used - before,
            latest_block=latest,
        )
