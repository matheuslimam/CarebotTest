import os
from typing import Final
from flask import Flask, request
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from asgiref.wsgi import WsgiToAsgi  # Importa o adaptador WSGI para ASGI

# Configurações do bot
print("Inicializando o bot...")
BOT_TOKEN: Final = os.getenv("BOT_TOKEN", "YOUR TOKEN HERE")
RENDER_EXTERNAL_URL: Final = os.getenv("RENDER_EXTERNAL_URL")
BOT_HANDLE: Final = "@your_bot_handle"

if not BOT_TOKEN or not RENDER_EXTERNAL_URL:
    raise ValueError("As variáveis de ambiente BOT_TOKEN e RENDER_EXTERNAL_URL devem estar configuradas.")

WEBHOOK_URL: Final = f"{RENDER_EXTERNAL_URL}/webhook/{BOT_TOKEN}"

# Inicializa o Flask
app_flask = Flask(__name__)
telegram_app = Application.builder().token(BOT_TOKEN).build()

# Comandos do bot
async def initiate_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print("Handler /start acionado.")  # Log adicional
    await update.message.reply_text("Olá! Eu sou seu bot. Como posso ajudar?")

async def assist_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print("Handler /help acionado.")  # Log adicional
    await update.message.reply_text("Aqui está a ajuda!")

async def personalize_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print("Handler /custom acionado.")  # Log adicional
    await update.message.reply_text("Comando personalizado adicionado com sucesso.")

# Geração de respostas
def generate_response(user_input: str) -> str:
    normalized_input = user_input.lower()

    if "oi" in normalized_input:
        return "Olá!"

    if "como você está" in normalized_input:
        return "Estou funcionando perfeitamente!"

    if "quero assinar" in normalized_input:
        return "Claro, vamos lá!"

    return "Desculpe, não entendi. Pode reformular?"

# Processa mensagens
async def process_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    print(f"Handler de mensagem acionado. Mensagem: {text}")  # Log adicional
    response = generate_response(text)
    print("Resposta do bot:", response)
    await update.message.reply_text(response)

# Log de erros
async def log_error(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print(f"Erro no update {update}: {context.error}")

# Rota do webhook
@app_flask.route(f"/webhook/{BOT_TOKEN}", methods=["POST"])
def webhook():
    try:
        # Log do update bruto recebido do Telegram
        json_update = request.get_json(force=True)
        print(f"Recebido update bruto: {json_update}")  # Log para verificar o update

        # Decodifica o update para o formato esperado pelo bot
        update = Update.de_json(json_update, telegram_app.bot)
        print("Update decodificado com sucesso.")  # Log após a decodificação

        # Adiciona o update à fila para processamento
        telegram_app.update_queue.put_nowait(update)
        print("Update adicionado à fila do bot.")  # Log confirmando a adição à fila

        return "OK", 200
    except Exception as e:
        # Log detalhado para erros
        print(f"Erro no webhook: {e}")
        return f"Erro no webhook: {e}", 500


# Configuração do webhook
async def set_webhook():
    try:
        await telegram_app.bot.set_webhook(WEBHOOK_URL)
        print(f"Webhook configurado com sucesso: {WEBHOOK_URL}")
    except Exception as e:
        print(f"Erro ao configurar o webhook: {e}")

if __name__ == "__main__":
    import asyncio
    from uvicorn import run

    async def initialize():
        print("Configurando webhook e inicializando o bot...")
        await set_webhook()  # Configura o webhook
        await telegram_app.initialize()  # Inicializa o bot
        print("Bot inicializado. Iniciando processamento da fila...")
        await telegram_app.start()  # Inicia o processamento da fila de updates


    asyncio.run(initialize())

    # Registra handlers
    telegram_app.add_handler(CommandHandler("start", initiate_command))
    telegram_app.add_handler(CommandHandler("help", assist_command))
    telegram_app.add_handler(CommandHandler("custom", personalize_command))
    telegram_app.add_handler(MessageHandler(filters.TEXT, process_message))
    telegram_app.add_error_handler(log_error)
    print("Handlers configurados e registrados.")

    asgi_app = WsgiToAsgi(app_flask)
    run(asgi_app, host="0.0.0.0", port=int(os.getenv("PORT", 5000)))
