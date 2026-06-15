"""Action Read — turn a raw signal into "so what should I do?".

The hard truth this layer encodes: a signal's *actionability depends on who and
how*. A market maker receiving tokens is usually inventory/LP (non-directional),
while several funds accumulating the same token is a real directional signal.
Conflating them is what makes most "smart money" bots noise.

Output is decision *support* — stance, actionability, a framework play, and
confirm/invalidate conditions — never a definitive buy/sell call. It also serves
as the structured context fed to the optional Surf Chat AI layer.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

from alphatide.core.models import Alert, AlertKind

MM_TYPES = {"market_maker", "market-maker"}
FUND_TYPES = {"fund", "vc"}

_DISCLAIMER = "Not financial advice — interpretation only; on-chain signals can mislead."


@dataclass
class ActionRead:
    stance: str          # Bullish-lean / Bearish-lean / Neutral / Attention only / Mixed
    actionability: str   # low | medium | high
    meaning: str
    play: str
    confirm: str
    invalidate: str
    risk: str = _DISCLAIMER


def _smart_money(a: Alert) -> ActionRead:
    et = (a.extra.get("entity_type") or "").lower()
    direction = a.extra.get("direction", "accumulate")
    acc = direction == "accumulate"

    if et in MM_TYPES:
        return ActionRead(
            stance="Neutral (non-directional)",
            actionability="low",
            meaning="A market maker's flow is usually inventory / liquidity / hedging, "
                    "not a directional bet on the token.",
            play="Treat as operational noise. Don't trade off this alone.",
            confirm="Upgrade only if *funds* (not MMs) accumulate the same token, or "
                    "price breaks out on rising volume.",
            invalidate="Offsetting flow back to the MM within hours = pure market making.",
        )
    if et in FUND_TYPES:
        return ActionRead(
            stance="Bullish-lean" if acc else "Bearish-lean",
            actionability="medium",
            meaning=f"A fund is {'accumulating' if acc else 'distributing'} this token "
                    "on Mantle — potentially directional.",
            play=("Watch for a pullback entry if you share the thesis; size small."
                  if acc else "Consider trimming exposure / tightening stops if long."),
            confirm="Same wallet or other funds add in the same direction; mindshare/volume rising.",
            invalidate="The wallet reverses within the session, or it's a known LP/unlock move.",
        )
    # whale / trader / smart_money
    return ActionRead(
        stance="Bullish-lean" if acc else "Bearish-lean",
        actionability="medium" if et in {"smart_money", "smart-money", "trader"} else "low",
        meaning=f"A tracked {'smart-money' if et else 'large'} wallet is "
                f"{'accumulating' if acc else 'distributing'} this token.",
        play="Use as a watch-trigger, not a standalone entry.",
        confirm="A second labeled wallet follows the same direction (convergence).",
        invalidate="No follow-through from other tracked wallets within a few hours.",
    )


def _convergence(a: Alert) -> ActionRead:
    acc = a.extra.get("direction") == "accumulate"
    n = a.extra.get("n_entities", 2)
    return ActionRead(
        stance="Bullish-lean" if acc else "Mixed / rotation",
        actionability="high" if acc else "medium",
        meaning=f"{n} distinct smart-money entities moved the same token the same way "
                "this window — coordinated accumulation is the strongest directional read here.",
        play="Highest-conviction setup the bot produces. If you share the thesis, "
             "stage a position into pullbacks; scale with confirmation."
             if acc else "Mixed direction — wait for the rotation to resolve.",
        confirm="More entities join the same side; price/volume/mindshare turn up together.",
        invalidate="Entities flip to distributing, or the move traces to an unlock/airdrop.",
    )


def _inflow(a: Alert) -> ActionRead:
    et = (a.extra.get("entity_type") or "").lower()
    if et == "cex":
        return ActionRead(
            stance="Mild accumulation (context-dependent)",
            actionability="low",
            meaning="Capital is leaving a CEX into a Mantle wallet — often withdrawal to "
                    "self-custody / deploy, but can also be operational.",
            play="Note as ecosystem inflow; not a standalone trade.",
            confirm="The receiving wallet then deploys into a token a fund is also buying.",
            invalidate="Funds quickly route back to the CEX (just internal movement).",
        )
    return ActionRead(
        stance="Neutral-to-bullish for the chain",
        actionability="low",
        meaning="Capital is bridging into Mantle — ecosystem-level inflow, not token-specific.",
        play="Macro context for Mantle activity; pair with token-level signals.",
        confirm="Bridged capital shows up in DEX buys of specific tokens.",
        invalidate="Inflow is a single protocol/treasury move, not broad.",
    )


def _anomaly(a: Alert) -> ActionRead:
    spike = a.extra.get("zscore", 0) > 0
    return ActionRead(
        stance="Attention only",
        actionability="low",
        meaning=f"Unusual volume {'spike' if spike else 'drop'} — flags attention but says "
                "nothing about direction by itself.",
        play="Run /whale on the token to see *who* is behind it; that's the real signal.",
        confirm="A labeled fund/convergence is found driving the volume.",
        invalidate="Volume is one large wash/relay with no labeled actor.",
    )


_BUILDERS = {
    AlertKind.SMART_MONEY: _smart_money,
    AlertKind.CONVERGENCE: _convergence,
    AlertKind.INFLOW: _inflow,
    AlertKind.ANOMALY: _anomaly,
}


def build_read(alert: Alert) -> ActionRead:
    return _BUILDERS[alert.kind](alert)


def attach_read(alert: Alert) -> Alert:
    """Attach the rule-based read to an alert (free, deterministic)."""
    alert.read = asdict(build_read(alert))
    return alert


def is_high_conviction(alert: Alert) -> bool:
    """Whether an alert is worth spending Surf Chat credits on."""
    read = alert.read or asdict(build_read(alert))
    return read.get("actionability") == "high"


_AI_SYSTEM = (
    "You are a crypto trading analyst reading a single on-chain signal on the "
    "Mantle network. In 2-3 short sentences, explain what it likely means and how "
    "a trader might frame an action, with explicit risk. Distinguish market-maker "
    "flow (non-directional) from fund accumulation. Never give a definitive buy/sell "
    "call — interpretation only. Plain text, no preamble."
)


def _ai_prompt(alert: Alert) -> str:
    r = alert.read or {}
    parts = [
        f"Signal: {alert.headline} (kind={alert.kind.value}, score={alert.score}).",
        f"Detail: {alert.detail}",
        f"Rule-based read — stance: {r.get('stance')}, actionability: "
        f"{r.get('actionability')}; meaning: {r.get('meaning')}",
        "Write the trader's action read.",
    ]
    return "\n".join(parts)


def attach_ai_note(alert: Alert, surf) -> Alert:
    """Add a Surf Chat AI interpretation to a high-conviction alert (budget-gated)."""
    if alert.read is None:
        attach_read(alert)
    note = surf.chat(_AI_SYSTEM, _ai_prompt(alert))
    if note:
        alert.ai_note = note
    return alert
