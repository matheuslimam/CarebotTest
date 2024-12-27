import os
from flask import Flask, request
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters
from asgiref.wsgi import WsgiToAsgi  # Importa o adaptador WSGI para ASGI

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
    try:
        user_name = update.effective_user.first_name
        print(f"Handler /start acionado para {user_name}")
        await update.message.reply_text(f"Olá, {user_name}! Eu sou seu bot.")
    except Exception as e:
        print(f"Erro no handler /start: {e}")

async def echo(update: Update, context):
    """Handler para mensagens de texto"""
    try:
        user_name = update.effective_user.first_name
        message = update.message.text
        print(f"Handler echo acionado para mensagem: {message} de {user_name}")
        await update.message.reply_text(f"Você disse: {message}")
    except Exception as e:
        print(f"Erro no handler echo: {e}")

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

    # Configura o webhook e inicializa o bot
    async def initialize():
        print("Configurando webhook e inicializando o bot...")
        await set_webhook()
        await telegram_app.initialize()
        print("Bot inicializado com sucesso.")

    # Inicializa o bot
    asyncio.run(initialize())

    # Adapta o Flask para ASGI usando WsgiToAsgi
    asgi_app = WsgiToAsgi(app_flask)

    # Inicia o servidor com Uvicorn
    print("Iniciando o servidor com Uvicorn...")
    run(asgi_app, host="0.0.0.0", port=int(os.getenv("PORT", 5000)))
