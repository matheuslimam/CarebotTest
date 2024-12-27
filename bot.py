import logging
import os
import traceback
from typing import Final

import asyncio
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
from uvicorn import run

# -------------------------------------------------------------
# 1) Configuração de logging em modo DEBUG
# -------------------------------------------------------------
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.DEBUG  # <-- DEBUG mostra detalhes de todo o fluxo
)
logger = logging.getLogger(__name__)

# -------------------------------------------------------------
# 2) Variáveis de ambiente
# -------------------------------------------------------------
print("Inicializando o bot...")

BOT_TOKEN: Final = os.getenv("BOT_TOKEN", "YOUR TOKEN HERE")
RENDER_EXTERNAL_URL: Final = os.getenv("RENDER_EXTERNAL_URL")

if not BOT_TOKEN or not RENDER_EXTERNAL_URL:
    raise ValueError("As variáveis BOT_TOKEN e RENDER_EXTERNAL_URL devem estar configuradas.")

WEBHOOK_URL = f"{RENDER_EXTERNAL_URL}/webhook/{BOT_TOKEN}"

# -------------------------------------------------------------
# 3) Flask + PTB Application
# -------------------------------------------------------------
app_flask = Flask(__name__)
telegram_app = Application.builder().token(BOT_TOKEN).build()

# -------------------------------------------------------------
# 4) Funções de Handler
# -------------------------------------------------------------
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info("Handler /start acionado.")
    await update.message.reply_text("Olá, eu sou seu bot!")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info("Handler /help acionado.")
    await update.message.reply_text("Esta é a ajuda do bot.")

def generate_response(user_input: str) -> str:
    """Gera uma resposta simples com base no que o usuário digitou."""
    normalized = user_input.lower()

    # Trate "ola", "olá" e "oi"
    if "ola" in normalized or "olá" in normalized or "oi" in normalized:
        return "Olá, tudo bem?"
    elif "como você está" in normalized:
        return "Estou funcionando perfeitamente!"
    elif "quero assinar" in normalized:
        return "Claro, vamos lá!"
    
    return "Desculpe, não entendi. Pode reformular?"

async def process_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler de mensagem de texto."""
    text = update.message.text
    logger.debug(f"process_message chamado. Mensagem do usuário: {text}")
    
    response = generate_response(text)
    await update.message.reply_text(response)

async def log_error(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler global de erros. Loga exceções."""
    logger.error(f"Erro no update {update}: {context.error}")
    traceback.print_exc()

# -------------------------------------------------------------
# 5) Webhook: Rota síncrona, usando update_queue
# -------------------------------------------------------------
@app_flask.route(f"/webhook/{BOT_TOKEN}", methods=["POST"])
def webhook():
    try:
        json_update = request.get_json(force=True)
        logger.info(f"Recebido update bruto: {json_update}")

        update = Update.de_json(json_update, telegram_app.bot)
        logger.info("Update decodificado com sucesso.")

        # Adiciona o update na fila do PTB
        telegram_app.update_queue.put_nowait(update)
        logger.info("Update adicionado à fila do bot (update_queue).")

        return "OK", 200
    except Exception as e:
        logger.error(f"Erro no webhook: {e}")
        traceback.print_exc()
        return f"Erro no webhook: {e}", 500

# -------------------------------------------------------------
# 6) Configuração de webhook e inicialização
# -------------------------------------------------------------
async def set_webhook():
    """Configura o webhook do Telegram."""
    try:
        await telegram_app.bot.set_webhook(WEBHOOK_URL)
        logger.info(f"Webhook configurado: {WEBHOOK_URL}")
    except Exception as e:
        logger.error(f"Erro ao configurar webhook: {e}")
        traceback.print_exc()

if __name__ == "__main__":
    # ---------------------------------------------------------
    # 6.1: Registra todos os handlers ANTES de iniciar
    # ---------------------------------------------------------
    telegram_app.add_handler(CommandHandler("start", start_command))
    telegram_app.add_handler(CommandHandler("help", help_command))
    telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, process_message))
    telegram_app.add_error_handler(log_error)

    async def initialize():
        """Função de inicialização assíncrona."""
        logger.info("Configurando webhook e inicializando o bot...")
        await set_webhook()
        await telegram_app.initialize()
        logger.info("Bot inicializado. Iniciando processamento da fila...")
        await telegram_app.start()

    # Executa a inicialização e depois sobe o servidor
    asyncio.run(initialize())

    # Converte o Flask p/ ASGI e roda com uvicorn
    asgi_app = WsgiToAsgi(app_flask)
    run(asgi_app, host="0.0.0.0", port=int(os.getenv("PORT", "5000")))