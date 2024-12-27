import logging
import os
import traceback
import asyncio
from typing import Final

from flask import Flask, request
from asgiref.wsgi import WsgiToAsgi
from uvicorn import run

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes
)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.DEBUG
)
logger = logging.getLogger(__name__)


# ---------------------------
# Variáveis de ambiente
# ---------------------------
BOT_TOKEN: Final = os.getenv("BOT_TOKEN", "YOUR TOKEN HERE")
RENDER_EXTERNAL_URL: Final = os.getenv("RENDER_EXTERNAL_URL")

if not BOT_TOKEN or not RENDER_EXTERNAL_URL:
    raise ValueError("As variáveis BOT_TOKEN e RENDER_EXTERNAL_URL devem estar configuradas.")

WEBHOOK_URL = f"{RENDER_EXTERNAL_URL}/webhook/{BOT_TOKEN}"

app_flask = Flask(__name__)

# Cria a aplicação do PTB
telegram_app = Application.builder().token(BOT_TOKEN).build()


# ---------------------------
# Handlers
# ---------------------------
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info("Handler /start acionado.")
    await update.message.reply_text("Olá! Eu sou seu bot via process_update().")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info("Handler /help acionado.")
    await update.message.reply_text("Exemplo de bot usando process_update().")

def generate_response(user_input: str) -> str:
    user_input = user_input.lower()
    if "ola" in user_input or "olá" in user_input or "oi" in user_input:
        return "Olá, tudo bem?"
    return "Não entendi…"

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    logger.debug(f"process_message chamado: {text}")
    resp = generate_response(text)
    await update.message.reply_text(resp)

async def log_error(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Erro no update {update}: {context.error}")
    traceback.print_exc()


# ---------------------------
# Webhook Rota (ASSÍNCRONA)
# ---------------------------
@app_flask.route(f"/webhook/{BOT_TOKEN}", methods=["POST"])
async def webhook():
    """
    Rota assíncrona que processa diretamente o update chamando application.process_update.
    Não usa fila, então não precisamos do telegram_app.start().
    """
    try:
        json_update = request.get_json(force=True)
        logger.info(f"Recebido update bruto: {json_update}")

        update = Update.de_json(json_update, telegram_app.bot)
        logger.info("Update decodificado com sucesso.")

        # Processa imediatamente, sem passar pela fila
        await telegram_app.process_update(update)
        logger.info("Update processado diretamente.")
        return "OK", 200
    except Exception as e:
        logger.error(f"Erro no webhook: {e}")
        traceback.print_exc()
        return f"Erro no webhook: {e}", 500


# ---------------------------
# Configurar webhook & rodar
# ---------------------------
async def set_webhook():
    try:
        await telegram_app.bot.set_webhook(WEBHOOK_URL)
        logger.info(f"Webhook configurado: {WEBHOOK_URL}")
    except Exception as e:
        logger.error(f"Erro ao configurar webhook: {e}")
        traceback.print_exc()

if __name__ == "__main__":
    # Registra handlers
    telegram_app.add_handler(CommandHandler("start", start_command))
    telegram_app.add_handler(CommandHandler("help", help_command))
    telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    telegram_app.add_error_handler(log_error)

    async def initialize():
        logger.info("Configurando webhook e inicializando o bot...")
        await set_webhook()
        # IMPORTANTE: com process_update, não precisamos de .start() para a fila
        await telegram_app.initialize()
        logger.info("Bot inicializado. (process_update em uso).")

        # Teste de envio de mensagem (opcional):
        # await telegram_app.bot.send_message(chat_id=SEU_CHAT_ID, text="Bot subiu com process_update().")

    asyncio.run(initialize())

    # Converte para ASGI e roda com uvicorn
    asgi_app = WsgiToAsgi(app_flask)
    run(asgi_app, host="0.0.0.0", port=int(os.getenv("PORT", "5000")))