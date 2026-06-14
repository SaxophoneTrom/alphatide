"""Signal scoring.

A signal's score blends three things a trader actually cares about:
  1. how *big* the move was (USD, log-scaled — $1M isn't 100x more alarming
     than $10k, it's ~2.5x),
  2. *who* did it (a named fund/MM bleeding into Mantle >> an unlabeled whale),
  3. label *confidence*.

Kept pure and deterministic so it's unit-testable.
"""

from __future__ import annotations

import math

from alphatide.core.models import AddressLabel

# Weight by entity type — how much "alpha" the identity itself carries.
ENTITY_WEIGHT: dict[str, float] = {
    "fund": 1.0,
    "vc": 1.0,
    "market_maker": 0.95,
    "market-maker": 0.95,
    "smart_money": 0.9,
    "smart-money": 0.9,
    "trader": 0.75,
    "whale": 0.7,
    "cex": 0.6,  # CEX flows matter but are noisier
}

# Infrastructure / non-actor labels that are NEVER smart money. A DEX pool or a
# token contract trips the USD threshold on every swap, but it isn't an actor —
# excluding these by type is what keeps signals clean.
NON_ACTOR_TYPES: frozenset[str] = frozenset({
    "dex", "token", "contract", "smart-contract", "smart_contract",
    "smart-contract-platform", "protocol", "nft", "bridge",
})


def entity_weight(label: AddressLabel) -> float:
    """Smart-money weight for an identity. 0 for anonymous or non-actor labels.

    No "any label gets a little weight" fallback — that let DEX pools and token
    contracts leak in. Only explicitly recognized actor types score.
    """
    if not label.is_labeled:
        return 0.0
    return ENTITY_WEIGHT.get((label.entity_type or "").lower(), 0.0)


def size_factor(amount_usd: float) -> float:
    """Log-scaled size in [0, ~1.5]. $10k≈0, $100k≈0.5, $1M≈1.0, $10M≈1.5."""
    if amount_usd <= 10_000:
        return 0.0
    return min(1.5, math.log10(amount_usd / 10_000) / 2.0)


def score_signal(label: AddressLabel, amount_usd: float) -> float:
    """Return a 0–100 score."""
    w = entity_weight(label)
    if w == 0.0:
        return 0.0
    base = 50.0 * w                       # identity carries up to 50 pts
    size = 35.0 * size_factor(amount_usd) # size carries up to ~52 pts (capped below)
    conf = 15.0 * max(label.confidence, 0.5 if label.entity_name else 0.0)
    return round(min(100.0, base + size + conf), 1)


def build_reason(label: AddressLabel, token: str, amount_usd: float, action: str) -> str:
    who = label.entity_name or (label.labels[0] if label.labels else "Labeled wallet")
    kind = f" ({label.entity_type})" if label.entity_type else ""
    return (
        f"{who}{kind} — known cross-chain smart money — just {action} "
        f"~${amount_usd:,.0f} of {token} on Mantle."
    )
