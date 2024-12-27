import os
from flask import Flask, request
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters

# Inicializa o Flask para gerenciar webhooks
app_flask = Flask(__name__)

# Configurações do bot
BOT_TOKEN = os.getenv("BOT_TOKEN")  # Token do bot
RENDER_EXTERNAL_URL = os.getenv("RENDER_EXTERNAL_URL")  # URL base do Render
if not BOT_TOKEN or not RENDER_EXTERNAL_URL:
    raise ValueError("As variáveis de ambiente BOT_TOKEN e RENDER_EXTERNAL_URL devem estar configuradas.")

WEBHOOK_URL = f"{RENDER_EXTERNAL_URL}/webhook/{BOT_TOKEN}"  # URL completa do webhook

# Configuração do Telegram Bot
telegram_app = ApplicationBuilder().token(BOT_TOKEN).build()

# Funções de Comando e Handlers
async def start(update: Update, context):
    """Comando /start"""
    user_name = update.effective_user.first_name
    print(f"Comando /start recebido de {user_name}")
    await update.message.reply_text("Olá! Eu sou seu bot.")

async def echo(update: Update, context):
    """Responde com a mesma mensagem enviada pelo usuário."""
    user_name = update.effective_user.first_name
    message_text = update.message.text
    print(f"Mensagem recebida: {message_text} de {user_name}")
    await update.message.reply_text(f"Você disse: {message_text}")

# Adiciona handlers ao bot
telegram_app.add_handler(CommandHandler("start", start))
telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo))
print("Handlers adicionados com sucesso.")

# Rota do Webhook
@app_flask.route(f"/webhook/{BOT_TOKEN}", methods=["POST"])
def webhook():
    """Recebe mensagens do Telegram via webhook."""
    try:
        json_update = request.get_json(force=True)
        print(f"Recebido update: {json_update}")  # Log do update recebido
        update = Update.de_json(json_update, telegram_app.bot)
        telegram_app.update_queue.put_nowait(update)
        print("Update adicionado à fila.")
        return "OK", 200
    except Exception as e:
        print(f"Erro no Webhook: {e}")  # Loga erros no webhook
        return f"Erro no Webhook: {e}", 500

# Função para configurar o Webhook
async def set_webhook():
    """Configura o webhook no Telegram."""
    try:
        await telegram_app.bot.set_webhook(WEBHOOK_URL)
        print(f"Webhook configurado com sucesso: {WEBHOOK_URL}")
    except Exception as e:
        print(f"Erro ao configurar o webhook: {e}")

if __name__ == "__main__":
    import asyncio

    # Configura o webhook
    print("Configurando o webhook...")
    asyncio.run(set_webhook())

    # Inicia o servidor Flask
    print("Iniciando o servidor Flask...")
    app_flask.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)))
