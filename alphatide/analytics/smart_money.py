"""Cross-chain smart money detector (AlphaTide's core / idea 7-A).

A Mantle address means nothing until Surf tells us it's Wintermute / Jump / a
known fund on Ethereum/Base. We only spend credits on addresses that already
cleared the on-chain USD trigger.

In the detector suite this consumes the shared DetectionContext (movers +
labels resolved once for the whole cycle), so it adds no extra Surf calls.
A standalone `detect(events, min_usd)` is kept for tests and one-off use.
"""

from __future__ import annotations

from alphatide.analytics.scoring import build_reason, entity_weight, score_signal
from alphatide.core.config import settings
from alphatide.core.models import (
    Action,
    Alert,
    AddressLabel,
    DetectionContext,
    SmartMoneySignal,
    TransferEvent,
)
from alphatide.data.mantle_client import large_movers
from alphatide.data.surf_client import SurfClient

# Entity types this detector owns. Bridges/CEXes are handled by the inflow
# detector instead, so the labeled space is partitioned (minimal overlap).
SMART_TYPES = {
    "fund", "vc", "market_maker", "market-maker",
    "smart_money", "smart-money", "whale", "trader",
}


def _infer_action(addr: str, evs: list[TransferEvent]) -> tuple[Action, TransferEvent]:
    top = max(evs, key=lambda e: e.amount_usd)
    if addr == top.to_addr:
        return Action.RECEIVE, top
    return Action.SEND, top


def signals_from_context(ctx: DetectionContext) -> list[SmartMoneySignal]:
    """Build smart money signals from already-resolved movers + labels."""
    out: list[SmartMoneySignal] = []
    for addr, evs in ctx.movers.items():
        label = ctx.labels.get(addr)
        if label is None or not label.is_labeled:
            continue
        etype = (label.entity_type or "").lower()
        if etype not in SMART_TYPES and entity_weight(label) < 0.4:
            continue
        # leave pure bridge/cex to the inflow detector
        if etype in ("bridge", "cex"):
            continue
        action, top = _infer_action(addr, evs)
        agg_usd = sum(e.amount_usd for e in evs)
        score = score_signal(label, agg_usd)
        if score <= 0:
            continue
        out.append(
            SmartMoneySignal(
                address=addr,
                label=label,
                action=action,
                token_symbol=top.token_symbol,
                amount_usd=agg_usd,
                score=score,
                reason=build_reason(label, top.token_symbol, agg_usd, action.value),
                tx_hash=top.tx_hash,
                block=top.block,
            )
        )
    out.sort(key=lambda s: s.score, reverse=True)
    return out


class CrossChainSmartMoneyDetector:
    name = "smart_money"

    def __init__(self, surf: SurfClient | None = None) -> None:
        self.surf = surf or SurfClient()

    def detect_ctx(self, ctx: DetectionContext) -> list[Alert]:
        return [s.to_alert() for s in signals_from_context(ctx)]

    # --- standalone (tests / one-off): builds movers + labels itself ---
    def detect(
        self, events: list[TransferEvent], min_usd: float | None = None
    ) -> list[SmartMoneySignal]:
        min_usd = settings.min_candidate_usd if min_usd is None else min_usd
        movers = large_movers(events, min_usd)
        if not movers:
            return []
        labels = self.surf.label_addresses(list(movers.keys()))
        ctx = DetectionContext(
            events=events, movers=movers, labels=labels, min_usd=min_usd
        )
        return signals_from_context(ctx)
