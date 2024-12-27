import os
from flask import Flask, request
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters

# Inicializa o Flask para gerenciar webhooks
app_flask = Flask(__name__)

# Configurações do bot
BOT_TOKEN = os.getenv("BOT_TOKEN")  # Token armazenado como variável de ambiente
RENDER_EXTERNAL_URL = os.getenv("RENDER_EXTERNAL_URL")  # URL base do Render
WEBHOOK_URL = f"{RENDER_EXTERNAL_URL}/webhook/{BOT_TOKEN}"  # URL completa do webhook

if not BOT_TOKEN or not RENDER_EXTERNAL_URL:
    raise ValueError("As variáveis de ambiente BOT_TOKEN e RENDER_EXTERNAL_URL devem estar configuradas.")

# Configuração do Telegram Bot
app = ApplicationBuilder().token(BOT_TOKEN).build()


# Funções de Comando e Handlers
async def start(update: Update, context):
    """Comando /start"""
    await update.message.reply_text("Olá! Eu sou seu bot.")

async def echo(update: Update, context):
    """Responde com a mesma mensagem enviada pelo usuário."""
    await update.message.reply_text(f"Você disse: {update.message.text}")


# Adiciona handlers ao bot
app.add_handler(CommandHandler("start", start))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo))


# Rota do Webhook
@app_flask.route(f"/webhook/{BOT_TOKEN}", methods=["POST"])
def webhook():
    """Recebe mensagens do Telegram via webhook."""
    try:
        json_update = request.get_json(force=True)
        update = Update.de_json(json_update, app.bot)
        app.update_queue.put_nowait(update)
        return "OK", 200
    except Exception as e:
        return f"Erro no Webhook: {e}", 500


# Função para configurar o Webhook
async def set_webhook():
    """Configura o webhook no Telegram."""
    try:
        await app.bot.set_webhook(WEBHOOK_URL)
        print(f"Webhook configurado com sucesso: {WEBHOOK_URL}")
    except Exception as e:
        print(f"Erro ao configurar o webhook: {e}")


if __name__ == "__main__":
    # Configura o webhook antes de iniciar o servidor Flask
    import asyncio

    print("Configurando o webhook...")
    asyncio.run(set_webhook())

    # Inicia o servidor Flask
    print("Iniciando o servidor Flask...")
    app_flask.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)))
