"""Mantle network data access via JSON-RPC.

The watcher harvests large ERC-20 movements straight from `eth_getLogs`, decodes
the Transfer topic, applies a USD threshold, and returns clean candidate
addresses. Logic verified live against rpc.mantle.xyz (chainId 5000, ~2s blocks)
on 2026-06-13.

Dependency-light on purpose: uses stdlib JSON-RPC so the watcher runs anywhere.
`get_web3()` is kept for richer queries (balances, contract calls) when needed.
"""

from __future__ import annotations

import json
import urllib.request
from collections import defaultdict

from alphatide.core.config import settings
from alphatide.core.models import TransferEvent
from alphatide.data.tokens import TOKENS, get_token

# keccak256("Transfer(address,address,uint256)")
TRANSFER_TOPIC = (
    "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
)
# A correctly left-padded 20-byte address inside a 32-byte topic.
_ADDR_PAD = "0x000000000000000000000000"
_ZERO = "0x" + "0" * 40


class MantleClient:
    def __init__(self, rpc_url: str | None = None) -> None:
        self.rpc_url = rpc_url or settings.mantle_rpc_url

    # --- raw JSON-RPC ---
    def _rpc(self, method: str, params: list) -> dict:
        body = json.dumps(
            {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
        ).encode()
        req = urllib.request.Request(
            self.rpc_url, data=body, headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=40) as r:
            out = json.load(r)
        if "error" in out:
            raise RuntimeError(f"RPC error: {out['error']}")
        return out["result"]

    def latest_block(self) -> int:
        return int(self._rpc("eth_blockNumber", []), 16)

    # --- log harvesting ---
    @staticmethod
    def _topic_to_addr(topic: str) -> str | None:
        """Return a 0x address only if the topic is a clean left-padded address."""
        if not topic.startswith(_ADDR_PAD):
            return None  # not an address (filters poison / non-address topics)
        return "0x" + topic[-40:]

    def fetch_transfers(
        self, token_symbol: str, from_block: int, to_block: int
    ) -> list[TransferEvent]:
        token = TOKENS.get(token_symbol)
        if token is None:
            return []
        logs = self._rpc(
            "eth_getLogs",
            [
                {
                    "fromBlock": hex(from_block),
                    "toBlock": hex(to_block),
                    "address": token.address,
                    "topics": [TRANSFER_TOPIC],
                }
            ],
        )
        events: list[TransferEvent] = []
        price = token.usd_hint if not token.is_stable else 1.0
        for lg in logs:
            topics = lg.get("topics", [])
            if len(topics) < 3:
                continue
            frm = self._topic_to_addr(topics[1])
            to = self._topic_to_addr(topics[2])
            if not frm or not to:
                continue
            try:
                raw = int(lg["data"], 16)
            except (ValueError, KeyError):
                continue
            amount = raw / (10 ** token.decimals)
            events.append(
                TransferEvent(
                    tx_hash=lg.get("transactionHash", ""),
                    block=int(lg.get("blockNumber", "0x0"), 16),
                    token_symbol=token.symbol,
                    token_address=token.address,
                    from_addr=frm,
                    to_addr=to,
                    amount=amount,
                    amount_usd=amount * price,
                )
            )
        return events

    def scan_recent(
        self, window: int | None = None, tokens: list[str] | None = None
    ) -> list[TransferEvent]:
        """Scan the last `window` blocks across the token watchlist."""
        window = window or settings.scan_block_window
        tokens = tokens or list(TOKENS.keys())
        latest = self.latest_block()
        frm = max(0, latest - window)
        out: list[TransferEvent] = []
        for sym in tokens:
            try:
                out.extend(self.fetch_transfers(sym, frm, latest))
            except Exception:
                # one token failing shouldn't kill the whole scan
                continue
        return out


def large_movers(
    events: list[TransferEvent], min_usd: float
) -> dict[str, list[TransferEvent]]:
    """Group large transfers by the *non-zero* counterparty addresses.

    Aggregates per-address so a wallet that made several big moves is one
    candidate, not many. Zero address (mint/burn) is dropped.
    """
    by_addr: dict[str, list[TransferEvent]] = defaultdict(list)
    for ev in events:
        if ev.amount_usd < min_usd:
            continue
        for addr in (ev.from_addr, ev.to_addr):
            if addr == _ZERO:
                continue
            by_addr[addr].append(ev)
    return dict(by_addr)


def get_web3():
    """Full web3 client for richer on-chain calls (balances, contracts)."""
    from web3 import Web3

    return Web3(Web3.HTTPProvider(settings.mantle_rpc_url))
