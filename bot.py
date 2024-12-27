import os
import asyncio
import logging
import traceback

from flask import Flask, request
from asgiref.wsgi import WsgiToAsgi
from uvicorn import Config, Server

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes
)

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN", "YOUR_TOKEN_HERE")
RENDER_EXTERNAL_URL = os.getenv("RENDER_EXTERNAL_URL", "YOUR_URL_HERE")
WEBHOOK_PATH = f"/webhook/{BOT_TOKEN}"
WEBHOOK_URL = f"{RENDER_EXTERNAL_URL}{WEBHOOK_PATH}"

app_flask = Flask(__name__)
telegram_app = Application.builder().token(BOT_TOKEN).build()


@app_flask.route(WEBHOOK_PATH, methods=["POST"])
def webhook():
    """Rota SÍNCRONA do Flask para receber updates e colocar na fila."""
    try:
        data = request.get_json(force=True)
        logger.info(f"Recebido update bruto: {data}")

        update = Update.de_json(data, telegram_app.bot)
        logger.info("Update decodificado com sucesso.")

        telegram_app.update_queue.put_nowait(update)
        logger.info("Update adicionado à fila do bot (update_queue).")
    except Exception as e:
        logger.error(f"Erro no webhook: {e}")
        traceback.print_exc()
    return "OK", 200


# --------------------------
# Handlers
# --------------------------
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Olá! Sou seu bot + Uvicorn em loop único.")

async def echo_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    await update.message.reply_text(f"Você disse: {text}")

async def log_error(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Erro no update {update}: {context.error}")
    traceback.print_exc()


async def set_webhook():
    await telegram_app.bot.set_webhook(WEBHOOK_URL)
    logger.info(f"Webhook definido: {WEBHOOK_URL}")


async def main():
    """
    Função principal que inicia:
      1) o PTB (Application) e seu loop interno
      2) o servidor Uvicorn, tudo no mesmo event loop
    """
    # 1. Registra handlers
    telegram_app.add_handler(CommandHandler("start", start_command))
    telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo_message))
    telegram_app.add_error_handler(log_error)

    # 2. Configura webhook
    await set_webhook()

    # 3. Inicializa o PTB
    await telegram_app.initialize()

    # 4. Inicia o PTB *em segundo plano*
    #    Obs.: se chamarmos await telegram_app.start(), o código bloquearia.
    #    Então vamos criar uma *task* para que o PTB fique rodando "paralelamente".
    asyncio.create_task(telegram_app.start())

    # 5. Inicia o Uvicorn via Config+Server, sem usar uvicorn.run()
    asgi_app = WsgiToAsgi(app_flask)

    config = Config(
        app=asgi_app,
        host="0.0.0.0",
        port=int(os.getenv("PORT", "5000")),
        loop="asyncio",   # Garante que usaremos o loop atual
        lifespan="off",   # Desativa suporte ao 'lifespan' events do ASGI
    )
    server = Server(config)

    # Uvicorn passa a rodar *no* loop atual
    logger.info("Iniciando Uvicorn + Bot no mesmo event loop ...")
    await server.serve()

    # Se o servidor encerrar, paramos o bot:
    logger.info("Servidor Uvicorn parado. Encerrando bot.")
    await telegram_app.stop()


if __name__ == "__main__":
    # Executa tudo em um só event loop
    asyncio.run(main())