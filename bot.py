import os
from flask import Flask, request
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters

# Inicializa o Flask
app_flask = Flask(__name__)

# Configurações do bot
BOT_TOKEN = os.getenv("BOT_TOKEN")
RENDER_EXTERNAL_URL = os.getenv("RENDER_EXTERNAL_URL")
if not BOT_TOKEN or not RENDER_EXTERNAL_URL:
    raise ValueError("As variáveis de ambiente BOT_TOKEN e RENDER_EXTERNAL_URL devem estar configuradas.")

WEBHOOK_URL = f"{RENDER_EXTERNAL_URL}/webhook/{BOT_TOKEN}"

# Configuração do bot
telegram_app = Application.builder().token(BOT_TOKEN).build()

# Handlers
async def start(update: Update, context):
    """Handler para o comando /start"""
    user_name = update.effective_user.first_name
    print(f"/start recebido de {user_name}")
    await update.message.reply_text(f"Olá, {user_name}! Eu sou seu bot.")

async def echo(update: Update, context):
    """Handler para mensagens de texto"""
    user_name = update.effective_user.first_name
    message = update.message.text
    print(f"Mensagem recebida: {message} de {user_name}")
    await update.message.reply_text(f"Você disse: {message}")

# Adiciona os handlers
telegram_app.add_handler(CommandHandler("start", start))
telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo))
print("Handlers configurados.")

# Rota do Webhook
@app_flask.route(f"/webhook/{BOT_TOKEN}", methods=["POST"])
def webhook():
    """Recebe mensagens do Telegram via webhook"""
    try:
        json_update = request.get_json(force=True)
        print(f"Recebido update: {json_update}")
        update = Update.de_json(json_update, telegram_app.bot)
        telegram_app.update_queue.put_nowait(update)
        print("Update processado com sucesso.")
        return "OK", 200
    except Exception as e:
        print(f"Erro no webhook: {e}")
        return f"Erro no webhook: {e}", 500

# Configuração do Webhook
async def set_webhook():
    """Configura o webhook no Telegram"""
    try:
        await telegram_app.bot.set_webhook(WEBHOOK_URL)
        print(f"Webhook configurado: {WEBHOOK_URL}")
    except Exception as e:
        print(f"Erro ao configurar o webhook: {e}")

if __name__ == "__main__":
    import asyncio
    from uvicorn import run

    # Configura o webhook
    print("Configurando webhook...")
    asyncio.run(set_webhook())

    # Inicia o servidor com Uvicorn
    print("Iniciando o servidor com Uvicorn...")
    run(app_flask, host="0.0.0.0", port=int(os.getenv("PORT", 5000)))
