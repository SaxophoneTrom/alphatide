"""Background monitor: periodically run a detection cycle and push new signals.

Deduplicates by (address, tx_hash) so the same move isn't alerted twice.
Registered as a JobQueue task on the Telegram application.
"""

from __future__ import annotations

import logging

from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from alphatide.bot.formatting import format_signal
from alphatide.pipeline import AlphaTidePipeline

logger = logging.getLogger(__name__)


async def monitor_tick(context: ContextTypes.DEFAULT_TYPE) -> None:
    app = context.application
    pipe: AlphaTidePipeline = app.bot_data.setdefault("pipeline", AlphaTidePipeline())
    seen: set[str] = app.bot_data.setdefault("seen_signals", set())
    subscribers: set[int] = app.bot_data.setdefault("subscribers", set())

    try:
        res = pipe.run_cycle()
    except Exception as exc:  # never let a bad cycle kill the loop
        logger.warning("monitor cycle failed: %s", exc)
        return

    fresh = [s for s in res.signals if f"{s.address}:{s.tx_hash}" not in seen]
    for s in fresh:
        seen.add(f"{s.address}:{s.tx_hash}")

    if not fresh or not subscribers:
        return

    for chat_id in list(subscribers):
        for s in fresh[:3]:
            try:
                await context.bot.send_message(
                    chat_id, format_signal(s), parse_mode=ParseMode.MARKDOWN,
                    disable_web_page_preview=True,
                )
            except Exception as exc:
                logger.warning("push to %s failed: %s", chat_id, exc)
