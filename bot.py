import logging
import os
import asyncio
import traceback
from typing import Final

from flask import Flask, request
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes
)
from asgiref.wsgi import WsgiToAsgi
from uvicorn import run

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.DEBUG
)

logger = logging.getLogger(__name__)

print("Inicializando o bot...")

BOT_TOKEN: Final = os.getenv("BOT_TOKEN", "YOUR TOKEN HERE")
RENDER_EXTERNAL_URL: Final = os.getenv("RENDER_EXTERNAL_URL")
if not BOT_TOKEN or not RENDER_EXTERNAL_URL:
    raise ValueError("BOT_TOKEN e RENDER_EXTERNAL_URL precisam estar configurados.")

WEBHOOK_URL = f"{RENDER_EXTERNAL_URL}/webhook/{BOT_TOKEN}"

app_flask = Flask(__name__)
telegram_app = Application.builder().token(BOT_TOKEN).build()

# 1) HANDLERS -----------------------------
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info("Handler /start acionado.")
    await update.message.reply_text("Olá, sou seu bot!")

def generate_response(user_input: str) -> str:
    if "oi" in user_input.lower():
        return "Olá!"
    return "Não entendi…"

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    logger.debug(f"process_message chamado: {text}")
    response = generate_response(text)
    await update.message.reply_text(response)

async def log_error(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Erro no update {update}: {context.error}")
    traceback.print_exc()

# 2) WEBHOOK ROUTE -----------------------------
@app_flask.route(f"/webhook/{BOT_TOKEN}", methods=["POST"])
def webhook():
    try:
        json_update = request.get_json(force=True)
        logger.info(f"Recebido update bruto: {json_update}")

        update = Update.de_json(json_update, telegram_app.bot)
        logger.info("Update decodificado com sucesso.")

        telegram_app.update_queue.put_nowait(update)
        logger.info("Update adicionado à fila do bot (update_queue).")

        return "OK", 200
    except Exception as e:
        logger.error(f"Erro no webhook: {e}")
        traceback.print_exc()
        return f"Erro no webhook: {e}", 500

# 3) SET WEBHOOK -----------------------------
async def set_webhook():
    try:
        await telegram_app.bot.set_webhook(WEBHOOK_URL)
        logger.info(f"Webhook configurado: {WEBHOOK_URL}")
    except Exception as e:
        logger.error(f"Erro ao configurar webhook: {e}")
        traceback.print_exc()

# 4) MAIN ------------------------------------
if __name__ == "__main__":
    # Adicionar handlers ANTES de iniciar
    telegram_app.add_handler(CommandHandler("start", start_command))
    telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    telegram_app.add_error_handler(log_error)

    async def initialize():
        logger.info("Configurando webhook e inicializando o bot...")
        await set_webhook()
        await telegram_app.initialize()
        logger.info("Bot inicializado. Iniciando processamento da fila…")
        await telegram_app.start()

    asyncio.run(initialize())

    asgi_app = WsgiToAsgi(app_flask)
    run(asgi_app, host="0.0.0.0", port=int(os.getenv("PORT", "5000")))