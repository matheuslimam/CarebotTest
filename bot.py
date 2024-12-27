# bot.py
import os, logging, asyncio, traceback
from flask import Flask, request
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from asgiref.wsgi import WsgiToAsgi
from uvicorn import run

logging.basicConfig(level=logging.DEBUG)

app_flask = Flask(__name__)
BOT_TOKEN = os.getenv("BOT_TOKEN")
RENDER_EXTERNAL_URL = os.getenv("RENDER_EXTERNAL_URL")
WEBHOOK_URL = f"{RENDER_EXTERNAL_URL}/webhook/{BOT_TOKEN}"

telegram_app = Application.builder().token(BOT_TOKEN).build()

@app_flask.route(f"/webhook/{BOT_TOKEN}", methods=["POST"])
def webhook():
    try:
        json_update = request.get_json(force=True)
        update = Update.de_json(json_update, telegram_app.bot)
        logging.info("Recebido update, colocando na fila do PTB.")
        telegram_app.update_queue.put_nowait(update)
    except Exception as e:
        logging.error(f"Erro no webhook: {e}")
        traceback.print_exc()
    return "OK", 200

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Olá! Sou seu bot usando update_queue.")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Responde baseado no texto
    text = update.message.text.lower()
    if "oi" in text or "olá" in text:
        await update.message.reply_text("Olá, tudo bem?")
    else:
        await update.message.reply_text("Não entendi…")

async def log_error(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logging.error(f"Erro: {context.error}")
    traceback.print_exc()

async def set_webhook():
    await telegram_app.bot.set_webhook(WEBHOOK_URL)
    logging.info(f"Webhook definido: {WEBHOOK_URL}")

async def main():
    # 1) Registra os handlers
    telegram_app.add_handler(CommandHandler("start", start_command))
    telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    telegram_app.add_error_handler(log_error)

    # 2) Configura webhook
    await set_webhook()

    # 3) Inicia o bot (loop interno) que processa a fila update_queue
    await telegram_app.initialize()
    await telegram_app.start()

    # 4) Sobe o Flask/ASGI
    asgi_app = WsgiToAsgi(app_flask)
    run(asgi_app, host="0.0.0.0", port=int(os.getenv("PORT", "5000")))

if __name__ == "__main__":
    asyncio.run(main())