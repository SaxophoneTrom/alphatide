"""Telegram command handlers.

Thin layer: each handler runs a pipeline cycle (or a focused query) and replies
with formatted output. The detector suite (7-A smart money, B convergence,
C inflow, I anomaly) all surface through the unified Alert stream.
"""

from __future__ import annotations

import logging

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from alphatide.analytics.action_read import attach_ai_note, is_high_conviction
from alphatide.bot.formatting import format_alert, format_digest
from alphatide.bot.keyboards import build_track_keyboard
from alphatide.bot.state import load_recent_alerts
from alphatide.core.models import AddressLabel
from alphatide.core.config import settings
from alphatide.core.models import AlertKind
from alphatide.data.tokens import TOKENS
from alphatide.pipeline import AlphaTidePipeline

logger = logging.getLogger(__name__)

WELCOME = (
    "🌊 *AlphaTide*\n"
    "I watch Mantle and name the smart money the moment it moves here — "
    "funds, market makers and whales known from Ethereum/Base, powered by Surf.\n\n"
    "*What I detect*\n"
    "🧠 known smart money active on Mantle\n"
    "🧲 several smart-money entities converging on one token\n"
    "🌉 bridges/CEXes pushing capital into Mantle\n"
    "📈 statistical volume anomalies\n\n"
    "*Commands*\n"
    "/alpha — top signals on Mantle now\n"
    "/scan — run a fresh detection cycle (stats)\n"
    "/recent — the last alerts I pushed\n"
    "/demo — show what a live high-conviction alert looks like\n"
    "/whale `<TOKEN>` — recent smart money in a token (e.g. /whale mETH)\n"
    "/track `<address>` — who is this wallet? (Surf cross-chain label)\n"
    "/subscribe — get pushed alerts as they happen\n"
)

_KIND_EMOJI = {
    "smart_money": "🧠", "convergence": "🧲", "inflow": "🌉", "anomaly": "📈",
}


def _pipeline(context: ContextTypes.DEFAULT_TYPE) -> AlphaTidePipeline:
    pipe = context.application.bot_data.get("pipeline")
    if pipe is None:
        pipe = AlphaTidePipeline()
        context.application.bot_data["pipeline"] = pipe
    return pipe


async def _rate_ok(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Per-user rate limit for expensive commands. Returns False if throttled."""
    rl = context.application.bot_data.get("rate_limiter")
    if rl is None:
        return True
    key = update.effective_chat.id
    if rl.allow(key):
        return True
    wait = rl.retry_after(key)
    await update.message.reply_text(
        f"⏳ Easy there — too many requests. Try again in ~{wait}s."
    )
    return False


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(WELCOME, parse_mode=ParseMode.MARKDOWN)


async def alpha(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _rate_ok(update, context):
        return
    await update.message.reply_text("🌊 Reading the tide on Mantle…")
    pipe = _pipeline(context)
    res = pipe.run_cycle()
    # AI read on the single strongest high-conviction alert (budget-gated)
    for a in res.alerts[:3]:
        if is_high_conviction(a):
            attach_ai_note(a, pipe.surf)
            break
    await update.message.reply_text(
        format_digest(res.alerts), parse_mode=ParseMode.MARKDOWN,
        disable_web_page_preview=True,
    )
    for a in res.alerts[:3]:
        await update.message.reply_text(
            format_alert(a), parse_mode=ParseMode.MARKDOWN,
            disable_web_page_preview=True, reply_markup=build_track_keyboard(a),
        )


async def scan(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _rate_ok(update, context):
        return
    res = _pipeline(context).run_cycle()
    counts: dict[str, int] = {}
    for a in res.alerts:
        counts[a.kind.value] = counts.get(a.kind.value, 0) + 1
    breakdown = ", ".join(f"{k}:{v}" for k, v in counts.items()) or "none"
    budget = context.application.bot_data.get("budget")
    budget_line = (
        f"\n• Surf budget left today: {budget.remaining()}/{budget.limit}"
        if budget is not None else ""
    )
    msg = (
        f"🔍 Scanned ~{res.scanned_events} transfers up to block {res.latest_block:,}\n"
        f"• {res.candidates} large movers (≥${settings.min_candidate_usd:,.0f})\n"
        f"• {len(res.alerts)} signals ({breakdown})\n"
        f"• {res.credits_used} Surf credits used{budget_line}"
    )
    await update.message.reply_text(msg)
    await update.message.reply_text(
        format_digest(res.alerts), parse_mode=ParseMode.MARKDOWN,
        disable_web_page_preview=True,
    )


async def whale(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _rate_ok(update, context):
        return
    if not context.args:
        await update.message.reply_text("Usage: /whale <TOKEN>  e.g. /whale mETH")
        return
    sym = context.args[0]
    match = next((k for k in TOKENS if k.lower() == sym.lower()), None)
    if not match:
        await update.message.reply_text(f"Unknown token. Tracked: {', '.join(TOKENS)}")
        return
    res = _pipeline(context).run_cycle()
    hits = [
        a for a in res.alerts
        if a.token == match and a.kind in (AlertKind.SMART_MONEY, AlertKind.CONVERGENCE, AlertKind.INFLOW)
    ]
    await update.message.reply_text(
        format_digest(hits), parse_mode=ParseMode.MARKDOWN,
        disable_web_page_preview=True,
    )


def _format_identity(addr: str, label: AddressLabel | None) -> str:
    if label and label.is_labeled:
        who = label.entity_name or "—"
        extra = f" ({', '.join(label.labels)})" if label.labels else ""
        return (
            f"🧠 `{addr}`\nSurf cross-chain identity: *{who}*{extra}\n"
            f"Type: {label.entity_type or 'n/a'}"
        )
    return f"`{addr}`\nNo cross-chain label on Surf — looks anonymous."


async def track(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _rate_ok(update, context):
        return
    if not context.args:
        await update.message.reply_text("Usage: /track <address>")
        return
    addr = context.args[0].lower()
    if not (addr.startswith("0x") and len(addr) == 42):
        await update.message.reply_text("That doesn't look like an address.")
        return
    labels = _pipeline(context).surf.label_addresses([addr])
    await update.message.reply_text(
        _format_identity(addr, labels.get(addr)), parse_mode=ParseMode.MARKDOWN,
    )


async def track_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle a tap on a '🔍 Track' inline button — look up and reply inline."""
    query = update.callback_query
    rl = context.application.bot_data.get("rate_limiter")
    if rl is not None and not rl.allow(query.from_user.id):
        await query.answer("⏳ Too many requests — wait a moment.", show_alert=False)
        return
    await query.answer("🔍 Looking up…")
    data = query.data or ""
    addr = data.split(":", 1)[1].lower() if ":" in data else ""
    if not (addr.startswith("0x") and len(addr) == 42):
        return
    labels = _pipeline(context).surf.label_addresses([addr])
    await query.message.reply_text(
        _format_identity(addr, labels.get(addr)), parse_mode=ParseMode.MARKDOWN,
    )


async def demo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show what a live, high-conviction AlphaTide alert looks like — on demand.

    Runs the canonical scenario (3 funds converging on mETH + a CEX inflow)
    through the REAL detector suite + Action Read, and attaches a live Surf AI
    read to the convergence. Clearly labeled as a simulation.
    """
    if not await _rate_ok(update, context):
        return
    owners = settings.owners
    if owners and update.effective_chat.id not in owners:
        await update.message.reply_text("🧪 /demo is restricted to the bot owner.")
        return

    from alphatide.demo import build_demo_alerts

    await update.message.reply_text(
        "🧪 *DEMO* — a simulated scenario showing what a live AlphaTide alert looks "
        "like. _Not real-time data._ Same detectors, Action Read, and Surf AI as production.",
        parse_mode=ParseMode.MARKDOWN,
    )
    pipe = _pipeline(context)
    alerts = build_demo_alerts()  # offline fixtures → deterministic labels
    for a in alerts[:3]:
        if is_high_conviction(a):
            attach_ai_note(a, pipe.surf)  # live Surf AI (budget-gated)
            if not a.ai_note:
                a.ai_note = (
                    "(sample) Three funds converging on mETH suggests coordinated "
                    "accumulation rather than market-making; consider staging into "
                    "pullbacks with tight risk. Not advice."
                )
            break
    await update.message.reply_text(
        format_digest(alerts), parse_mode=ParseMode.MARKDOWN,
        disable_web_page_preview=True,
    )
    for a in alerts[:3]:
        await update.message.reply_text(
            format_alert(a), parse_mode=ParseMode.MARKDOWN,
            disable_web_page_preview=True, reply_markup=build_track_keyboard(a),
        )


async def recent(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _rate_ok(update, context):
        return
    rows = load_recent_alerts(settings.alerts_file, n=10)
    if not rows:
        await update.message.reply_text(
            "No alerts pushed yet. I'll log every one here as it fires."
        )
        return
    lines = ["🌊 *Recent AlphaTide alerts*"]
    for r in rows:
        emoji = _KIND_EMOJI.get(r.get("kind", ""), "🌊")
        ts = (r.get("ts", "") or "").replace("T", " ")[5:16]  # MM-DD HH:MM
        lines.append(f"{emoji} `{ts}`  {r.get('headline', '')}  · *{r.get('score', '')}*")
    await update.message.reply_text(
        "\n".join(lines), parse_mode=ParseMode.MARKDOWN,
        disable_web_page_preview=True,
    )


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(WELCOME, parse_mode=ParseMode.MARKDOWN)
