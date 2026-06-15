"""AlphaTide Telegram bot entrypoint.

Run with: python -m alphatide.bot.main
Requires TELEGRAM_BOT_TOKEN in .env. SURF_API_KEY is optional — without it the
bot runs on Surf's anonymous free tier, then falls back to bundled fixtures.

The bot is public (anyone with the username can use it) so it ships with abuse
protection: per-user rate limiting and a shared daily Surf-credit ceiling.
Push subscriptions are persisted across restarts.
"""

from __future__ import annotations

import logging

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

from alphatide.bot import handlers
from alphatide.bot.monitor import monitor_tick
from alphatide.bot.state import load_subscribers, save_subscribers
from alphatide.core.config import settings
from alphatide.core.limits import DailyCreditBudget, RateLimiter
from alphatide.data.surf_client import SurfClient
from alphatide.pipeline import AlphaTidePipeline

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
    save_subscribers(settings.subscribers_file, subs)
    await update.message.reply_text(
        "🔔 Subscribed. I'll ping you when smart money moves on Mantle."
    )


async def unsubscribe(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    subs = context.application.bot_data.setdefault("subscribers", set())
    subs.discard(update.effective_chat.id)
    save_subscribers(settings.subscribers_file, subs)
    await update.message.reply_text("🔕 Unsubscribed.")


def build_application() -> Application:
    app = Application.builder().token(settings.telegram_bot_token).build()

    # shared, budget-guarded pipeline used by BOTH handlers and the monitor
    budget = DailyCreditBudget(settings.daily_credit_budget)
    surf = SurfClient(budget=budget)
    app.bot_data["budget"] = budget
    app.bot_data["pipeline"] = AlphaTidePipeline(surf=surf)
    app.bot_data["rate_limiter"] = RateLimiter(settings.rate_limit_per_min, 60)
    app.bot_data["subscribers"] = load_subscribers(settings.subscribers_file)
    logger.info(
        "loaded %d subscriber(s); daily credit budget=%d",
        len(app.bot_data["subscribers"]), settings.daily_credit_budget,
    )

    app.add_handler(CommandHandler(["start", "help"], handlers.start))
    app.add_handler(CommandHandler("alpha", handlers.alpha))
    app.add_handler(CommandHandler("scan", handlers.scan))
    app.add_handler(CommandHandler("recent", handlers.recent))
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
