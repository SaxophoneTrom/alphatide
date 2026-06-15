"""Core data models shared across AlphaTide.

These are plain dataclasses — no framework coupling — so the watcher, Surf
client, detector, and bot can all speak the same vocabulary.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Action(str, Enum):
    """What the candidate did on Mantle that made us look at them."""

    BUY = "buy"
    SELL = "sell"
    RECEIVE = "receive"
    SEND = "send"
    SWAP = "swap"


@dataclass(frozen=True)
class TransferEvent:
    """A single ERC-20 Transfer decoded from a Mantle log."""

    tx_hash: str
    block: int
    token_symbol: str
    token_address: str
    from_addr: str
    to_addr: str
    amount: float          # human units (decimals applied)
    amount_usd: float      # best-effort USD value

    @property
    def counterparties(self) -> tuple[str, str]:
        return (self.from_addr, self.to_addr)


@dataclass(frozen=True)
class AddressLabel:
    """Surf's verdict on who an address is (cross-chain)."""

    address: str
    entity_name: str | None = None
    entity_type: str | None = None
    labels: tuple[str, ...] = ()
    confidence: float = 0.0

    @property
    def is_labeled(self) -> bool:
        return bool(self.entity_name) or bool(self.labels)

    @classmethod
    def from_surf(cls, item: dict) -> "AddressLabel":
        raw_labels = item.get("labels") or []
        names = tuple(l.get("label") for l in raw_labels if l.get("label"))
        conf = max((l.get("confidence", 0) for l in raw_labels), default=0.0)
        return cls(
            address=(item.get("address") or "").lower(),
            entity_name=item.get("entity_name"),
            entity_type=item.get("entity_type"),
            labels=names,
            confidence=float(conf),
        )

    @classmethod
    def empty(cls, address: str) -> "AddressLabel":
        return cls(address=address.lower())


@dataclass
class SmartMoneySignal:
    """A ranked, ready-to-alert finding: known smart money active on Mantle."""

    address: str
    label: AddressLabel
    action: Action
    token_symbol: str
    amount_usd: float
    score: float
    reason: str
    tx_hash: str
    block: int
    enrichment: dict = field(default_factory=dict)

    @property
    def who(self) -> str:
        l = self.label
        if l.entity_name and l.labels:
            return f"{l.entity_name} ({', '.join(l.labels)})"
        if l.entity_name:
            return l.entity_name
        if l.labels:
            return ", ".join(l.labels)
        return "Unknown"

    def to_alert(self) -> "Alert":
        # receiving a token = accumulating it; sending = distributing
        direction = "accumulate" if self.action == Action.RECEIVE else "distribute"
        return Alert(
            kind=AlertKind.SMART_MONEY,
            score=self.score,
            headline=f"{self.who} — {self.action.value} ${self.amount_usd:,.0f} {self.token_symbol}",
            detail=self.reason,
            token=self.token_symbol,
            address=self.address,
            tx_hash=self.tx_hash,
            extra={
                "entity_type": self.label.entity_type,
                "direction": direction,
                "amount_usd": self.amount_usd,
            },
        )


class AlertKind(str, Enum):
    """The kinds of findings AlphaTide's detector suite can raise."""

    SMART_MONEY = "smart_money"   # 7-A: a known fund/MM/whale moved on Mantle
    CONVERGENCE = "convergence"   # B: several smart entities on the same token
    INFLOW = "inflow"             # C: a bridge/CEX is pushing capital into Mantle
    ANOMALY = "anomaly"           # I: token volume is statistically abnormal


@dataclass
class Alert:
    """A unified, ready-to-push finding from any detector."""

    kind: AlertKind
    score: float
    headline: str
    detail: str
    emoji: str = "🌊"
    token: str | None = None
    address: str | None = None
    tx_hash: str | None = None
    extra: dict = field(default_factory=dict)
    read: dict | None = None       # rule-based Action Read (stance/play/risk…)
    ai_note: str | None = None     # optional Surf Chat AI interpretation

    @property
    def dedup_key(self) -> str:
        return f"{self.kind.value}:{self.address or ''}:{self.token or ''}:{self.tx_hash or ''}"


@dataclass
class DetectionContext:
    """Shared inputs for one detection cycle.

    Built once per cycle so every detector reuses the same Mantle scan and the
    same (single, batched) Surf label lookup — no detector pays extra credits.
    """

    events: list[TransferEvent]
    movers: dict[str, list[TransferEvent]]   # large movers, by address
    labels: dict[str, AddressLabel]          # Surf identity for each mover
    min_usd: float
    volume_history: dict[str, list[float]] = field(default_factory=dict)
    latest_block: int = 0
