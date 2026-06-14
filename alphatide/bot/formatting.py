"""Telegram message formatting for AlphaTide signals.

Kept pure (string in / string out) so it's unit-testable without a bot running.
Uses Telegram-flavored Markdown.
"""

from __future__ import annotations

from alphatide.core.models import SmartMoneySignal

MANTLE_EXPLORER = "https://mantlescan.xyz"


def _emoji_for(entity_type: str | None) -> str:
    return {
        "fund": "🏦",
        "vc": "🏦",
        "market_maker": "⚙️",
        "market-maker": "⚙️",
        "smart_money": "🧠",
        "smart-money": "🧠",
        "cex": "🏛️",
        "whale": "🐋",
        "trader": "📈",
    }.get((entity_type or "").lower(), "🌊")


def _bar(score: float) -> str:
    filled = round(score / 10)
    return "█" * filled + "░" * (10 - filled)


def format_signal(s: SmartMoneySignal) -> str:
    emoji = _emoji_for(s.label.entity_type)
    short = f"{s.address[:6]}…{s.address[-4:]}"
    lines = [
        f"{emoji} *Smart money on Mantle* — score *{s.score}*",
        f"`{_bar(s.score)}`",
        "",
        f"*Who:* {s.who}",
        f"*Action:* {s.action.value.upper()} ~${s.amount_usd:,.0f} of {s.token_symbol}",
        f"*Address:* [{short}]({MANTLE_EXPLORER}/address/{s.address})",
    ]
    if s.tx_hash:
        lines.append(f"*Tx:* [{s.tx_hash[:10]}…]({MANTLE_EXPLORER}/tx/{s.tx_hash})")
    lines += ["", f"_{s.reason}_"]
    if s.enrichment.get("note"):
        lines.append(f"\n📊 {s.enrichment['note']}")
    return "\n".join(lines)


def format_digest(signals: list[SmartMoneySignal], limit: int = 5) -> str:
    if not signals:
        return "🌊 *AlphaTide* — no smart money signals on Mantle right now. The tide is calm."
    head = f"🌊 *AlphaTide* — top {min(limit, len(signals))} smart money signals on Mantle\n"
    rows = []
    for i, s in enumerate(signals[:limit], 1):
        emoji = _emoji_for(s.label.entity_type)
        rows.append(
            f"{i}. {emoji} *{s.who}* — {s.action.value} ${s.amount_usd:,.0f} "
            f"{s.token_symbol}  ·  score *{s.score}*"
        )
    return head + "\n".join(rows)
