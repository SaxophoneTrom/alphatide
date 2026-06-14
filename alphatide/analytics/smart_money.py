"""Cross-chain smart money detector (AlphaTide's core / idea 7-A).

Pipeline: large Mantle movers  →  Surf labels  →  keep only real smart money
→  score  →  ranked SmartMoneySignals.

The whole differentiator lives here: a Mantle address means nothing until Surf
tells us it's Wintermute / Jump / a known fund on Ethereum/Base. We only spend
credits on addresses that already cleared the on-chain USD trigger.
"""

from __future__ import annotations

from alphatide.core.config import settings
from alphatide.core.models import Action, SmartMoneySignal, TransferEvent
from alphatide.data.mantle_client import large_movers
from alphatide.data.surf_client import SurfClient
from alphatide.analytics.scoring import build_reason, entity_weight, score_signal


def _infer_action(addr: str, evs: list[TransferEvent]) -> tuple[Action, TransferEvent]:
    """Pick the most significant event and whether the address was buyer/seller."""
    top = max(evs, key=lambda e: e.amount_usd)
    if addr == top.to_addr:
        return Action.RECEIVE, top
    return Action.SEND, top


class CrossChainSmartMoneyDetector:
    def __init__(self, surf: SurfClient | None = None) -> None:
        self.surf = surf or SurfClient()

    def detect(
        self, events: list[TransferEvent], min_usd: float | None = None
    ) -> list[SmartMoneySignal]:
        min_usd = settings.min_candidate_usd if min_usd is None else min_usd

        # 1) on-chain trigger: only big movers become candidates
        movers = large_movers(events, min_usd)
        if not movers:
            return []

        # 2) one batched, cached Surf call resolves every candidate's identity
        labels = self.surf.label_addresses(list(movers.keys()))

        # 3) keep only addresses Surf flags as smart money; score them
        signals: list[SmartMoneySignal] = []
        smart_types = {t.lower() for t in settings.smart_entity_types}
        for addr, evs in movers.items():
            label = labels.get(addr)
            if label is None or not label.is_labeled:
                continue
            etype = (label.entity_type or "").lower()
            # accept known smart entity types, or any labeled wallet with weight
            if etype not in smart_types and entity_weight(label) < 0.4:
                continue

            action, top = _infer_action(addr, evs)
            agg_usd = sum(e.amount_usd for e in evs)
            score = score_signal(label, agg_usd)
            if score <= 0:
                continue
            signals.append(
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

        signals.sort(key=lambda s: s.score, reverse=True)
        return signals
