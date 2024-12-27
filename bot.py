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
# 1) Configuração de logging (importante para debug detalhado)
# -------------------------------------------------------------
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.DEBUG  # DEBUG para ver detalhes de todo o fluxo
)

logger = logging.getLogger(__name__)


# -------------------------------------------------------------
# 2) Variáveis de ambiente e Flask
# -------------------------------------------------------------
print("Inicializando o bot...")

BOT_TOKEN: Final = os.getenv("BOT_TOKEN")
RENDER_EXTERNAL_URL: Final = os.getenv("RENDER_EXTERNAL_URL")
if not BOT_TOKEN or not RENDER_EXTERNAL_URL:
    raise ValueError("As variáveis BOT_TOKEN e RENDER_EXTERNAL_URL devem estar configuradas.")

WEBHOOK_URL: Final = f"{RENDER_EXTERNAL_URL}/webhook/{BOT_TOKEN}"

app_flask = Flask(__name__)

# -------------------------------------------------------------
# 3) Cria a aplicação do python-telegram-bot
# -------------------------------------------------------------
telegram_app = Application.builder().token(BOT_TOKEN).build()


# -------------------------------------------------------------
# 4) Definição de comandos e handlers
# -------------------------------------------------------------
async def initiate_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info("Handler /start acionado.")
    await update.message.reply_text("Olá! Eu sou seu bot. Como posso ajudar?")

async def assist_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info("Handler /help acionado.")
    await update.message.reply_text("Aqui está a ajuda!")

async def personalize_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info("Handler /custom acionado.")
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
    # Log de debug para confirmar que o handler foi chamado
    logger.debug(f"process_message chamado. Mensagem do usuário: {update.message.text}")
    
    response = generate_response(update.message.text)
    await update.message.reply_text(response)

async def log_error(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Erro no update {update}: {context.error}")
    traceback.print_exc()


# -------------------------------------------------------------
# 5) Rota do webhook (síncrona, usa update_queue)
# -------------------------------------------------------------
@app_flask.route(f"/webhook/{BOT_TOKEN}", methods=["POST"])
def webhook():
    try:
        json_update = request.get_json(force=True)
        logger.info(f"Recebido update bruto: {json_update}")

        update = Update.de_json(json_update, telegram_app.bot)
        logger.info("Update decodificado com sucesso.")

        # Inserimos o update na fila do PTB
        telegram_app.update_queue.put_nowait(update)
        logger.info("Update adicionado à fila do bot (update_queue).")

        return "OK", 200
    except Exception as e:
        logger.error(f"Erro no webhook: {e}")
        traceback.print_exc()
        return f"Erro no webhook: {e}", 500


# -------------------------------------------------------------
# 6) Configuração do webhook e inicialização do bot
# -------------------------------------------------------------
async def set_webhook():
    try:
        await telegram_app.bot.set_webhook(WEBHOOK_URL)
        logger.info(f"Webhook configurado com sucesso: {WEBHOOK_URL}")
    except Exception as e:
        logger.error(f"Erro ao configurar o webhook: {e}")
        traceback.print_exc()


if __name__ == "__main__":
    # ---------------------------------------------------------
    # 6.1 Registra os handlers ANTES de iniciar o bot
    # ---------------------------------------------------------
    telegram_app.add_handler(CommandHandler("start", initiate_command))
    telegram_app.add_handler(CommandHandler("help", assist_command))
    telegram_app.add_handler(CommandHandler("custom", personalize_command))
    telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, process_message))
    telegram_app.add_error_handler(log_error)

    # (Opcional) Exemplo de "teste" para saber se o bot consegue enviar algo
    #  - É preciso definir um chat_id real e rodar esse send_message
    #  - Descomente e substitua SEU_CHAT_ID
    #
    # async def test_message():
    #     await telegram_app.bot.send_message(chat_id=SEU_CHAT_ID, text="Olá, estou vivo!")
    #

    async def initialize():
        logger.info("Configurando webhook e inicializando o bot...")
        await set_webhook()
        await telegram_app.initialize()
        logger.info("Bot inicializado. Iniciando processamento da fila...")
        await telegram_app.start()
        # Se quiser, pode chamar test_message() aqui:
        # await test_message()

    # ---------------------------------------------------------
    # 6.2 Executa rotinas assíncronas e inicia o servidor
    # ---------------------------------------------------------
    asyncio.run(initialize())

    asgi_app = WsgiToAsgi(app_flask)
    run(asgi_app, host="0.0.0.0", port=int(os.getenv("PORT", "5000")))