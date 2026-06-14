"""Convergence detector (idea B).

One whale is noise; three known funds piling into the same Mantle token in the
same window is a thesis. This reuses the cross-chain labels already resolved for
the cycle — zero extra Surf credits — and groups distinct smart-money entities
per token.
"""

from __future__ import annotations

from collections import defaultdict

from alphatide.core.models import Alert, AlertKind, DetectionContext

# entity types that count as "smart money converging"
CONVERGE_TYPES = {
    "fund", "vc", "market_maker", "market-maker",
    "smart_money", "smart-money", "whale", "trader",
}


class ConvergenceDetector:
    name = "convergence"

    def __init__(self, min_entities: int = 2) -> None:
        self.min_entities = min_entities

    def detect_ctx(self, ctx: DetectionContext) -> list[Alert]:
        # token -> {entity_name: usd}
        by_token: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
        by_token_dir: dict[str, dict[str, str]] = defaultdict(dict)

        for addr, evs in ctx.movers.items():
            label = ctx.labels.get(addr)
            if label is None or not label.is_labeled:
                continue
            etype = (label.entity_type or "").lower()
            if etype not in CONVERGE_TYPES:  # allowlist only — exclude DEX/contracts
                continue
            name = label.entity_name or (label.labels[0] if label.labels else addr[:10])
            for ev in evs:
                by_token[ev.token_symbol][name] += ev.amount_usd
                # crude direction: receiving = accumulate
                by_token_dir[ev.token_symbol][name] = (
                    "accumulating" if addr == ev.to_addr else "distributing"
                )

        alerts: list[Alert] = []
        for token, entities in by_token.items():
            if len(entities) < self.min_entities:
                continue
            total = sum(entities.values())
            names = sorted(entities, key=lambda n: -entities[n])
            # score: more distinct entities + bigger total → higher, capped 100
            score = min(100.0, 55.0 + 12.0 * (len(entities) - 1) + min(20.0, total / 1e5))
            dirs = by_token_dir[token]
            accumulating = sum(1 for n in names if dirs.get(n) == "accumulating")
            verb = "accumulating" if accumulating >= len(names) / 2 else "rotating"
            alerts.append(
                Alert(
                    kind=AlertKind.CONVERGENCE,
                    score=round(score, 1),
                    emoji="🧲",
                    headline=f"{len(entities)} smart-money entities {verb} {token}",
                    detail=(
                        f"{', '.join(names[:4])}"
                        f"{' and others' if len(names) > 4 else ''} "
                        f"moved a combined ~${total:,.0f} of {token} on Mantle in this window."
                    ),
                    token=token,
                    extra={"entities": names, "total_usd": total},
                )
            )
        alerts.sort(key=lambda a: a.score, reverse=True)
        return alerts
