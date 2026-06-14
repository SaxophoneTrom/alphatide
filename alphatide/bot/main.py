"""AlphaTide Telegram bot entrypoint.

Run with: python -m alphatide.bot.main
Requires TELEGRAM_BOT_TOKEN in .env. SURF_API_KEY is optional — without it the
bot runs on Surf's anonymous free tier, then falls back to bundled fixtures.
"""

from __future__ import annotations

import logging

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

from alphatide.bot import handlers
from alphatide.bot.monitor import monitor_tick
from alphatide.core.config import settings

logging.basicConfig(
    format="%(asctime)s %(name)s %(levelname)s %(message)s", level=logging.INFO
)
# httpx logs the full Telegram API URL (which embeds the bot token) on every
# poll. Quiet it so secrets never land in logs.
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("telegram.ext.Updater").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)


async def subscribe(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    subs = context.application.bot_data.setdefault("subscribers", set())
    subs.add(update.effective_chat.id)
    await update.message.reply_text(
        "🔔 Subscribed. I'll ping you when smart money moves on Mantle."
    )


async def unsubscribe(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    subs = context.application.bot_data.setdefault("subscribers", set())
    subs.discard(update.effective_chat.id)
    await update.message.reply_text("🔕 Unsubscribed.")


def build_application() -> Application:
    app = Application.builder().token(settings.telegram_bot_token).build()
    app.add_handler(CommandHandler(["start", "help"], handlers.start))
    app.add_handler(CommandHandler("alpha", handlers.alpha))
    app.add_handler(CommandHandler("scan", handlers.scan))
    app.add_handler(CommandHandler("whale", handlers.whale))
    app.add_handler(CommandHandler("track", handlers.track))
    app.add_handler(CommandHandler("subscribe", subscribe))
    app.add_handler(CommandHandler("unsubscribe", unsubscribe))
    if app.job_queue:
        app.job_queue.run_repeating(
            monitor_tick, interval=settings.monitor_interval, first=15
        )
    return app


def main() -> None:
    if not settings.telegram_bot_token:
        raise SystemExit(
            "TELEGRAM_BOT_TOKEN is not set — copy .env.example to .env and fill it in."
        )
    app = build_application()
    logger.info("AlphaTide bot starting (monitor every %ss)…", settings.monitor_interval)
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
