"""End-to-end orchestration: scan Mantle → detect cross-chain smart money.

This is the single entry point the bot, the monitor loop, and the demo all call.
Keeping it here means there's exactly one definition of "run a detection cycle".
"""

from __future__ import annotations

from dataclasses import dataclass

from alphatide.analytics.smart_money import CrossChainSmartMoneyDetector
from alphatide.core.config import settings
from alphatide.core.models import SmartMoneySignal, TransferEvent
from alphatide.data.mantle_client import MantleClient
from alphatide.data.surf_client import SurfClient


@dataclass
class CycleResult:
    signals: list[SmartMoneySignal]
    scanned_events: int
    candidates: int
    credits_used: int
    latest_block: int


class AlphaTidePipeline:
    def __init__(
        self,
        mantle: MantleClient | None = None,
        surf: SurfClient | None = None,
    ) -> None:
        self.mantle = mantle or MantleClient()
        self.surf = surf or SurfClient()
        self.detector = CrossChainSmartMoneyDetector(self.surf)

    def run_cycle(
        self, window: int | None = None, min_usd: float | None = None
    ) -> CycleResult:
        before = self.surf.credits_used
        latest = self.mantle.latest_block()
        events: list[TransferEvent] = self.mantle.scan_recent(window=window)
        signals = self.detector.detect(events, min_usd=min_usd)
        from alphatide.data.mantle_client import large_movers

        candidates = len(
            large_movers(
                events, settings.min_candidate_usd if min_usd is None else min_usd
            )
        )
        return CycleResult(
            signals=signals,
            scanned_events=len(events),
            candidates=candidates,
            credits_used=self.surf.credits_used - before,
            latest_block=latest,
        )
