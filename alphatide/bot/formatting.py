"""Telegram message formatting for AlphaTide alerts.

Kept pure (Alert in / string out) so it's unit-testable without a bot running.
One formatter renders every detector's output via the unified Alert type.
"""

from __future__ import annotations

from alphatide.core.models import Alert, AlertKind

MANTLE_EXPLORER = "https://mantlescan.xyz"

_KIND_LABEL = {
    AlertKind.SMART_MONEY: "Smart money on Mantle",
    AlertKind.CONVERGENCE: "Smart money convergence",
    AlertKind.INFLOW: "Capital inflow to Mantle",
    AlertKind.ANOMALY: "Volume anomaly",
}


def _bar(score: float) -> str:
    filled = max(0, min(10, round(score / 10)))
    return "█" * filled + "░" * (10 - filled)


def format_alert(a: Alert) -> str:
    title = _KIND_LABEL.get(a.kind, "Signal")
    lines = [
        f"{a.emoji} *{title}* — score *{a.score}*",
        f"`{_bar(a.score)}`",
        "",
        f"*{a.headline}*",
        "",
        f"_{a.detail}_",
    ]
    r = a.read or {}
    if r:
        act = (r.get("actionability") or "").upper()
        lines += [
            "",
            f"📖 *Read:* {r.get('stance')}  ·  actionability *{act}*",
            f"{r.get('meaning')}",
            f"💡 {r.get('play')}",
            f"✅ _Confirms if:_ {r.get('confirm')}",
            f"🛑 _Invalidated if:_ {r.get('invalidate')}",
            f"⚠️ _{r.get('risk')}_",
        ]
    if a.ai_note:
        lines += ["", f"🤖 *AI read (Surf):* {a.ai_note}"]
    refs = []
    if a.address:
        short = f"{a.address[:6]}…{a.address[-4:]}"
        refs.append(f"[{short}]({MANTLE_EXPLORER}/address/{a.address})")
    if a.tx_hash and a.tx_hash.startswith("0x") and len(a.tx_hash) > 12:
        refs.append(f"[tx]({MANTLE_EXPLORER}/tx/{a.tx_hash})")
    if refs:
        lines += ["", "  ·  ".join(refs)]
    return "\n".join(lines)


def format_digest(alerts: list[Alert], limit: int = 6) -> str:
    if not alerts:
        return (
            "🌊 *AlphaTide* — the tide is calm. No smart money, convergence, "
            "inflow or volume anomalies on Mantle right now."
        )
    head = f"🌊 *AlphaTide* — top {min(limit, len(alerts))} signals on Mantle\n"
    rows = []
    for i, a in enumerate(alerts[:limit], 1):
        act = (a.read or {}).get("actionability")
        tag = f"  · act:{act}" if act else ""
        rows.append(f"{i}. {a.emoji} {a.headline}  ·  *{a.score}*{tag}")
    return head + "\n".join(rows)
