from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters
import os
from flask import Flask, request

# Flask para lidar com webhooks
app_flask = Flask(__name__)

# Comando de início
async def start(update: Update, context):
    await update.message.reply_text("Olá! Eu sou seu bot.")

# Responde a mensagens
async def echo(update: Update, context):
    await update.message.reply_text(f"Você disse: {update.message.text}")

# Configuração do bot
BOT_TOKEN = os.getenv("BOT_TOKEN")  # Token armazenado como variável de ambiente
TELEGRAM_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"
WEBHOOK_URL = os.getenv("RENDER_EXTERNAL_URL") + f"/webhook/{BOT_TOKEN}"  # URL do Render

if __name__ == "__main__":
    # Configuração do bot usando ApplicationBuilder
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # Adiciona comandos e handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo))

    # Configuração de webhook
    @app_flask.route(f"/webhook/{BOT_TOKEN}", methods=["POST"])
    def webhook():
        """Endpoint para receber mensagens via webhook."""
        json_update = request.get_json(force=True)
        update = Update.de_json(json_update, app.bot)
        app.update_queue.put_nowait(update)
        return "OK"

    # Define o webhook
    async def set_webhook():
        await app.bot.set_webhook(WEBHOOK_URL)

    import asyncio
    asyncio.run(set_webhook())

    # Inicia o servidor Flask
    app_flask.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)))
