"""Capital inflow detector (idea C, label-based).

The literal "money entering Mantle, named." Rather than depend on a specific
bridge contract (Mantle's OP-stack predeploys emit nothing in practice), this
rides the proven transfer+label pipeline: when a Surf-labeled **bridge** or
**CEX** entity is the *sender* of a large transfer to a (typically fresh) Mantle
wallet, that's capital flowing in from a named source.

Zero extra Surf credits — it reuses the cycle's shared label lookup.
"""

from __future__ import annotations

from alphatide.core.models import Action, Alert, AlertKind, DetectionContext

INFLOW_TYPES = {"bridge", "cex"}

_ENTITY_EMOJI = {"bridge": "🌉", "cex": "🏛️"}


class InflowDetector:
    name = "inflow"

    def detect_ctx(self, ctx: DetectionContext) -> list[Alert]:
        alerts: list[Alert] = []
        for addr, evs in ctx.movers.items():
            label = ctx.labels.get(addr)
            if label is None or not label.is_labeled:
                continue
            etype = (label.entity_type or "").lower()
            if etype not in INFLOW_TYPES:
                continue
            # only outbound flow from the bridge/CEX = capital pushed INTO Mantle
            outbound = [e for e in evs if e.from_addr == addr]
            if not outbound:
                continue
            top = max(outbound, key=lambda e: e.amount_usd)
            total = sum(e.amount_usd for e in outbound)
            who = label.entity_name or (label.labels[0] if label.labels else "Bridge/CEX")
            # bigger flow → higher; CEX/bridge inflow caps a bit below smart-money
            score = round(min(90.0, 45.0 + min(45.0, total / 5e4)), 1)
            alerts.append(
                Alert(
                    kind=AlertKind.INFLOW,
                    score=score,
                    emoji=_ENTITY_EMOJI.get(etype, "💸"),
                    headline=f"{who} moving ${total:,.0f} {top.token_symbol} into Mantle",
                    detail=(
                        f"{who} ({etype}) sent ~${total:,.0f} of {top.token_symbol} to "
                        f"Mantle wallet(s) — fresh capital entering the chain from a named source."
                    ),
                    token=top.token_symbol,
                    address=addr,
                    tx_hash=top.tx_hash,
                    extra={"entity_type": etype, "action": Action.SEND.value},
                )
            )
        alerts.sort(key=lambda a: a.score, reverse=True)
        return alerts
