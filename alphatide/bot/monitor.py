"""Background monitor: periodically run a detection cycle and push new alerts.

Deduplicates by Alert.dedup_key so the same finding isn't pushed twice. Every
fresh alert is logged with its content AND appended to the JSONL history, so we
can always audit exactly what was pushed and when.
"""

from __future__ import annotations

import logging

from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from alphatide.analytics.action_read import attach_ai_note, is_high_conviction
from alphatide.bot.formatting import format_alert
from alphatide.bot.state import append_alert
from alphatide.core.config import settings
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

    # spend Surf Chat credits only on the single strongest high-conviction alert
    for a in fresh:
        if is_high_conviction(a):
            attach_ai_note(a, pipe.surf)
            break

    # heartbeat: only when there's something to say (avoids spamming quiet hours)
    if res.candidates or res.alerts:
        logger.info(
            "cycle: %d movers, %d alerts, %d fresh, %dcr",
            res.candidates, len(res.alerts), len(fresh), res.credits_used,
        )
    # record + log every fresh alert's content (auditable history)
    for a in fresh:
        logger.info("ALERT %s [%.1f] %s", a.kind.value, a.score, a.headline)
        try:
            append_alert(settings.alerts_file, a)
        except Exception as exc:
            logger.warning("alert history write failed: %s", exc)

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
