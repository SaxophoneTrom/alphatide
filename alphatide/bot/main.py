"""AlphaTide Telegram bot entrypoint.

Run with: python -m alphatide.bot.main
"""

import logging

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

from alphatide.core.config import settings

logging.basicConfig(
    format="%(asctime)s %(name)s %(levelname)s %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "🌊 AlphaTide is watching Mantle.\n"
        "Commands: /alpha /whale /track /anomaly /ask"
    )


def main() -> None:
    if not settings.telegram_bot_token:
        raise SystemExit("TELEGRAM_BOT_TOKEN is not set — copy .env.example to .env")

    app = Application.builder().token(settings.telegram_bot_token).build()
    app.add_handler(CommandHandler("start", start))
    # TODO: register /alpha, /whale, /track, /anomaly, /ask handlers

    logger.info("AlphaTide bot starting...")
    app.run_polling()


if __name__ == "__main__":
    main()
