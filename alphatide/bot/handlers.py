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

from alphatide.bot.formatting import format_alert, format_digest
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
    "/whale `<TOKEN>` — recent smart money in a token (e.g. /whale mETH)\n"
    "/track `<address>` — who is this wallet? (Surf cross-chain label)\n"
    "/subscribe — get pushed alerts as they happen\n"
)


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
    res = _pipeline(context).run_cycle()
    await update.message.reply_text(
        format_digest(res.alerts), parse_mode=ParseMode.MARKDOWN,
        disable_web_page_preview=True,
    )
    for a in res.alerts[:3]:
        await update.message.reply_text(
            format_alert(a), parse_mode=ParseMode.MARKDOWN,
            disable_web_page_preview=True,
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
    label = labels.get(addr)
    if label and label.is_labeled:
        who = label.entity_name or "—"
        extra = f" ({', '.join(label.labels)})" if label.labels else ""
        await update.message.reply_text(
            f"🧠 `{addr}`\nSurf cross-chain identity: *{who}*{extra}\n"
            f"Type: {label.entity_type or 'n/a'}",
            parse_mode=ParseMode.MARKDOWN,
        )
    else:
        await update.message.reply_text(
            f"`{addr}`\nNo cross-chain label on Surf — looks anonymous.",
            parse_mode=ParseMode.MARKDOWN,
        )


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(WELCOME, parse_mode=ParseMode.MARKDOWN)
