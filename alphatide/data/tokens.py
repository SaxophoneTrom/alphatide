"""Mantle token registry.

Addresses are the canonical Mantle mainnet (chainId 5000) contracts. `usd_hint`
is a coarse fallback price used only when no live price source is wired in;
stablecoins are pinned to 1.0. For non-stables a real deployment should pull
spot from Surf `market/price` or a Mantle DEX — see core/pricing.py.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Token:
    symbol: str
    address: str
    decimals: int
    is_stable: bool = False
    usd_hint: float = 0.0


# Lowercased addresses for easy comparison against decoded log topics.
TOKENS: dict[str, Token] = {
    "USDT": Token("USDT", "0x201eba5cc46d216ce6dc03f6a759e8e766e956ae", 6, True, 1.0),
    "USDC": Token("USDC", "0x09bc4e0d864854c6afb6eb9a9cdf58ac190d0df9", 6, True, 1.0),
    "WMNT": Token("WMNT", "0x78c1b0c915c4faa5fffa6cabf0219da63d7f4cb8", 18, False, 0.60),
    "mETH": Token("mETH", "0xcda86a272531e8640cd7f1a92c01839911b90bb0", 18, False, 3400.0),
    "WETH": Token("WETH", "0xdeaddeaddeaddeaddeaddeaadeaddeaddead0000", 18, False, 3300.0),
}

BY_ADDRESS: dict[str, Token] = {t.address: t for t in TOKENS.values()}


def get_token(address: str) -> Token | None:
    return BY_ADDRESS.get(address.lower())
