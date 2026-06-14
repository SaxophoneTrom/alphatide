"""Telegram command handlers.

Thin layer: each handler runs a pipeline cycle (or a focused query) and replies
with formatted output. The heavy lifting lives in pipeline/detector.
"""

from __future__ import annotations

import logging

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from alphatide.bot.formatting import format_digest, format_signal
from alphatide.core.config import settings
from alphatide.data.tokens import TOKENS
from alphatide.pipeline import AlphaTidePipeline

logger = logging.getLogger(__name__)

WELCOME = (
    "🌊 *AlphaTide*\n"
    "I watch Mantle and name the smart money the moment it moves here — "
    "funds, market makers and whales known from Ethereum/Base, powered by Surf.\n\n"
    "*Commands*\n"
    "/alpha — top cross-chain smart money signals on Mantle now\n"
    "/scan — run a fresh detection cycle\n"
    "/whale `<TOKEN>` — recent smart money in a token (e.g. /whale mETH)\n"
    "/track `<address>` — who is this wallet? (Surf cross-chain label)\n"
    "/help — this message"
)


def _pipeline(context: ContextTypes.DEFAULT_TYPE) -> AlphaTidePipeline:
    pipe = context.application.bot_data.get("pipeline")
    if pipe is None:
        pipe = AlphaTidePipeline()
        context.application.bot_data["pipeline"] = pipe
    return pipe


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(WELCOME, parse_mode=ParseMode.MARKDOWN)


async def alpha(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("🌊 Reading the tide on Mantle…")
    res = _pipeline(context).run_cycle()
    await update.message.reply_text(
        format_digest(res.signals), parse_mode=ParseMode.MARKDOWN,
        disable_web_page_preview=True,
    )
    for s in res.signals[:3]:
        await update.message.reply_text(
            format_signal(s), parse_mode=ParseMode.MARKDOWN,
            disable_web_page_preview=True,
        )


async def scan(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    res = _pipeline(context).run_cycle()
    msg = (
        f"🔍 Scanned ~{res.scanned_events} transfers up to block {res.latest_block:,}\n"
        f"• {res.candidates} large movers (≥${settings.min_candidate_usd:,.0f})\n"
        f"• {len(res.signals)} confirmed smart money\n"
        f"• {res.credits_used} Surf credits used"
    )
    await update.message.reply_text(msg)
    await update.message.reply_text(
        format_digest(res.signals), parse_mode=ParseMode.MARKDOWN,
        disable_web_page_preview=True,
    )


async def whale(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.message.reply_text("Usage: /whale <TOKEN>  e.g. /whale mETH")
        return
    sym = context.args[0]
    match = next((k for k in TOKENS if k.lower() == sym.lower()), None)
    if not match:
        await update.message.reply_text(
            f"Unknown token. Tracked: {', '.join(TOKENS)}"
        )
        return
    pipe = _pipeline(context)
    events = pipe.mantle.scan_recent(tokens=[match])
    signals = pipe.detector.detect(events)
    signals = [s for s in signals if s.token_symbol == match]
    await update.message.reply_text(
        format_digest(signals), parse_mode=ParseMode.MARKDOWN,
        disable_web_page_preview=True,
    )


async def track(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
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
