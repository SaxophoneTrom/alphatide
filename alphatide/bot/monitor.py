"""Background monitor: periodically run a detection cycle and push new alerts.

Deduplicates by Alert.dedup_key so the same finding isn't pushed twice.
Registered as a JobQueue task on the Telegram application.
"""

from __future__ import annotations

import logging

from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from alphatide.bot.formatting import format_alert
from alphatide.pipeline import AlphaTidePipeline

logger = logging.getLogger(__name__)


async def monitor_tick(context: ContextTypes.DEFAULT_TYPE) -> None:
    app = context.application
    pipe: AlphaTidePipeline = app.bot_data.setdefault("pipeline", AlphaTidePipeline())
    seen: set[str] = app.bot_data.setdefault("seen_alerts", set())
    subscribers: set[int] = app.bot_data.setdefault("subscribers", set())

    try:
        res = pipe.run_cycle()
    except Exception as exc:  # never let a bad cycle kill the loop
        logger.warning("monitor cycle failed: %s", exc)
        return

    fresh = [a for a in res.alerts if a.dedup_key not in seen]
    for a in fresh:
        seen.add(a.dedup_key)

    if fresh:
        logger.info("monitor: %d fresh alerts (%d credits)", len(fresh), res.credits_used)
    if not fresh or not subscribers:
        return

    for chat_id in list(subscribers):
        for a in fresh[:3]:
            try:
                await context.bot.send_message(
                    chat_id, format_alert(a), parse_mode=ParseMode.MARKDOWN,
                    disable_web_page_preview=True,
                )
            except Exception as exc:
                logger.warning("push to %s failed: %s", chat_id, exc)
