import uvicorn
import logging
import os
from pydantic_ai.messages import ModelMessage
from pydantic_ai import UsageLimits
from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from orchestrator import deps, orchestrator
from settings import get_settings

logging.basicConfig(
    format="%(asctime)s %(name)s %(levelname)s %(message)s", level=logging.INFO
)
# httpx logs every request URL at INFO, including the Telegram bot token.
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

settings = get_settings()

# Limite Telegram per singolo messaggio.
TG_MAX_LEN = 4096


def _chat_data(context: ContextTypes.DEFAULT_TYPE) -> dict:
    """chat_data è tipizzato Optional ma è sempre presente con l'Application di default."""
    assert context.chat_data is not None
    return context.chat_data


def _conversation_id(update: Update) -> str:
    """Namespace delle chiavi in Valkey: una conversazione per chat Telegram."""
    return f"tg:{update.effective_chat.id}"  # ty: ignore[unresolved-attribute]


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    _chat_data(context)["history"] = []
    await update.message.reply_text(  # ty: ignore[unresolved-attribute]
        "Conversazione azzerata. Chiedimi pure qualcosa sui dati."
    )


async def ask(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.message
    if message is None or not message.text:
        return

    chat_id = update.effective_chat.id  # ty: ignore[unresolved-attribute]
    await context.bot.send_chat_action(chat_id, ChatAction.TYPING)

    chat_data = _chat_data(context)
    history: list[ModelMessage] = chat_data.setdefault("history", [])
    try:
        result = await orchestrator.run(
            message.text,
            deps=deps,
            conversation_id=_conversation_id(update),
            message_history=history,
            usage_limits=UsageLimits(request_limit=30)
        )
    except Exception:
        logger.exception("Errore nella run dell'orchestrator per chat %s", chat_id)
        await message.reply_text("Si è verificato un errore, riprova più tardi.")
        return

    chat_data["history"] = result.all_messages()

    text = result.output or "Non ho una risposta."
    for i in range(0, len(text), TG_MAX_LEN):
        await message.reply_text(text[i : i + TG_MAX_LEN])


def main() -> None:
    if ((not settings.telegram) | (os.getenv('APP_EXPOSITION', None) == 'WEB' )):
        app = orchestrator.to_web()
        uvicorn.run(app, host="0.0.0.0", port=8000)
    else:
        app = (
            ApplicationBuilder()
            .token(settings.telegram.token.get_secret_value()) # ty: ignore[unresolved-attribute]
            .build()
        )
        app.add_handler(CommandHandler("start", start))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, ask))
        app.run_polling()


if __name__ == "__main__":
    main()
