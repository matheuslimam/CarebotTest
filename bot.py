import os
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
import asyncio
from uvicorn import run

print("Inicializando o bot...")

# Configurações do bot
BOT_TOKEN: Final = os.getenv("BOT_TOKEN", "YOUR TOKEN HERE")
RENDER_EXTERNAL_URL: Final = os.getenv("RENDER_EXTERNAL_URL")
if not BOT_TOKEN or not RENDER_EXTERNAL_URL:
    raise ValueError("BOT_TOKEN e RENDER_EXTERNAL_URL devem estar configurados.")

WEBHOOK_URL: Final = f"{RENDER_EXTERNAL_URL}/webhook/{BOT_TOKEN}"

app_flask = Flask(__name__)
telegram_app = Application.builder().token(BOT_TOKEN).build()

# -------------------------------------------------------------------
# Handlers
# -------------------------------------------------------------------
async def initiate_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Olá! Eu sou seu bot. Como posso ajudar?")

async def assist_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Aqui está a ajuda!")

async def personalize_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Comando personalizado adicionado com sucesso.")

def generate_response(user_input: str) -> str:
    normalized_input = user_input.lower()

    if "oi" in normalized_input:
        return "Olá!"
    if "como você está" in normalized_input:
        return "Estou funcionando perfeitamente!"
    if "quero assinar" in normalized_input:
        return "Claro, vamos lá!"
    return "Desculpe, não entendi. Pode reformular?"

async def process_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    response = generate_response(text)
    await update.message.reply_text(response)

async def log_error(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print(f"Erro no update {update}: {context.error}")

# -------------------------------------------------------------------
# Webhook: rota SÍNCRONA
# -------------------------------------------------------------------
@app_flask.route(f"/webhook/{BOT_TOKEN}", methods=["POST"])
def webhook():
    try:
        json_update = request.get_json(force=True)
        print(f"Recebido update bruto: {json_update}")

        update = Update.de_json(json_update, telegram_app.bot)
        print("Update decodificado com sucesso.")

        # Envia o update para o Application via queue
        telegram_app.update_queue.put_nowait(update)
        print("Update adicionado à fila do bot (update_queue).")

        return "OK", 200
    except Exception as e:
        print(f"Erro no webhook: {e}")
        return f"Erro no webhook: {e}", 500

# -------------------------------------------------------------------
# Configurações de webhook e inicialização
# -------------------------------------------------------------------
async def set_webhook():
    try:
        await telegram_app.bot.set_webhook(WEBHOOK_URL)
        print(f"Webhook configurado com sucesso: {WEBHOOK_URL}")
    except Exception as e:
        print(f"Erro ao configurar o webhook: {e}")

if __name__ == "__main__":
    telegram_app.add_handler(CommandHandler("start", initiate_command))
    telegram_app.add_handler(CommandHandler("help", assist_command))
    telegram_app.add_handler(CommandHandler("custom", personalize_command))
    telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, process_message))
    telegram_app.add_error_handler(log_error)

    async def initialize():
        print("Configurando webhook e inicializando o bot...")
        await set_webhook()
        await telegram_app.initialize()
        print("Bot inicializado. Iniciando processamento da fila...")
        await telegram_app.start()

    # Executa a inicialização assíncrona
    asyncio.run(initialize())

    # Sobe via WsgiToAsgi
    asgi_app = WsgiToAsgi(app_flask)
    run(asgi_app, host="0.0.0.0", port=int(os.getenv("PORT", "5000")))