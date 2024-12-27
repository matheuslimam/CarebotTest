import os
import asyncio
import logging
import traceback

from flask import Flask, request
from asgiref.wsgi import WsgiToAsgi
from uvicorn import Config, Server

from telegram import (
    Update,
    ReplyKeyboardMarkup,
    InlineKeyboardMarkup,
    InlineKeyboardButton
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes,
    ConversationHandler
)

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------
# Configurações de Token e URL (altere para seus valores)
# ---------------------------------------------------------------------
BOT_TOKEN = os.getenv("BOT_TOKEN", "YOUR_TOKEN_HERE")
RENDER_EXTERNAL_URL = os.getenv("RENDER_EXTERNAL_URL", "YOUR_URL_HERE")
WEBHOOK_PATH = f"/webhook/{BOT_TOKEN}"
WEBHOOK_URL = f"{RENDER_EXTERNAL_URL}{WEBHOOK_PATH}"

# ---------------------------------------------------------------------
# Inicialização do Flask e do Bot
# ---------------------------------------------------------------------
app_flask = Flask(__name__)
telegram_app = Application.builder().token(BOT_TOKEN).build()

@app_flask.route(WEBHOOK_PATH, methods=["POST"])
def webhook():
    """
    Rota SÍNCRONA do Flask para receber updates do Telegram
    e colocar na fila do Python Telegram Bot (PTB).
    """
    try:
        data = request.get_json(force=True)
        logger.info(f"Recebido update bruto: {data}")

        update = Update.de_json(data, telegram_app.bot)
        logger.info("Update decodificado com sucesso.")

        telegram_app.update_queue.put_nowait(update)
        logger.info("Update adicionado à fila do bot (update_queue).")
    except Exception as e:
        logger.error(f"Erro no webhook: {e}")
        traceback.print_exc()
    return "OK", 200

# ---------------------------------------------------------------------
# Definição dos estados e do fluxo de conversa
# ---------------------------------------------------------------------
WELCOME, SYMPTOMS, ANALYZE, PLAN, PAYMENT, EXAM, RESULT, SYMPTOMS_YES_NO = range(8)

symptoms_list = [
    "Cansaço", "Falta de Apetite", "Dor de Cabeça",
    "Náusea", "Tontura", "Palpitações",
    "Falta de Energia", "Insônia"
]

# Teclado de planos (ReplyKeyboard)
plans_keyboard = [["Gratuito", "Ouro", "Diamante"]]

# ---------------------------------------------------------------------
# Handlers de cada etapa
# ---------------------------------------------------------------------
async def welcome(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["symptoms"] = []
    context.user_data["current_symptom_index"] = 0
    await send_yes_no_question(update, context)
    return SYMPTOMS_YES_NO

async def send_yes_no_question(update: Update, context: ContextTypes.DEFAULT_TYPE):
    index = context.user_data.get("current_symptom_index", 0)
    if index >= len(symptoms_list):
        return await analyze(update, context)

    symptom = symptoms_list[index]
    keyboard = [
        [InlineKeyboardButton("Sim", callback_data="yes"), InlineKeyboardButton("Não", callback_data="no")]
    ]

    if update.callback_query:
        await update.callback_query.edit_message_text(
            text=f"Você está sentindo: {symptom}?",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    else:
        await update.message.reply_text(
            text=f"Você está sentindo: {symptom}?",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

async def symptoms_yes_no(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    response = query.data
    index = context.user_data.get("current_symptom_index", 0)

    if response == "yes":
        context.user_data["symptoms"].append(symptoms_list[index])

    context.user_data["current_symptom_index"] = index + 1
    await send_yes_no_question(update, context)
    return SYMPTOMS_YES_NO

async def analyze(update: Update, context: ContextTypes.DEFAULT_TYPE):
    symptoms = context.user_data.get("symptoms", [])
    if not symptoms:
        await update.callback_query.edit_message_text(
            "Nenhum sintoma selecionado. Por favor, reinicie o processo."
        )
        return ConversationHandler.END

    # Simulação de análise
    deficiencies = {
        "Cansaço": "Possível deficiência de ferro ou vitamina B12",
        "Falta de Apetite": "Possível deficiência de zinco",
        "Dor de Cabeça": "Pode estar relacionada à desidratação ou falta de magnésio",
        "Tontura": "Possível deficiência de ferro",
        "Palpitações": "Pode indicar falta de potássio ou magnésio",
    }

    analysis_results = [
        deficiencies.get(symptom, "Sem análise disponível") for symptom in symptoms
    ]
    results_text = "\n".join(
        f"- {symptom}: {result}" for symptom, result in zip(symptoms, analysis_results)
    )

    await update.callback_query.edit_message_text(
        text=f"Baseado nos sintomas informados, aqui está a análise inicial:\n{results_text}"
    )

    # Agora pergunta qual plano o usuário deseja
    chat_id = update.callback_query.message.chat_id
    await telegram_app.bot.send_message(
        chat_id=chat_id,
        text="Escolha um dos planos disponíveis para continuar.",
        reply_markup=ReplyKeyboardMarkup(plans_keyboard, one_time_keyboard=True, resize_keyboard=True),
    )
    return PLAN

async def plan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    plan_choice = update.message.text.strip()
    context.user_data["plan"] = plan_choice

    if plan_choice == "Gratuito":
        await update.message.reply_text("Aqui está uma prévia da sua prescrição básica.")
        return ConversationHandler.END

    elif plan_choice == "Ouro":
        await update.message.reply_text("Processando prescrição avançada...")
        return PAYMENT

    elif plan_choice == "Diamante":
        await update.message.reply_text(
            "Com o plano Diamante, você precisa realizar um exame de sangue. Vamos prosseguir."
        )
        return EXAM

    else:
        # Se digitou algo fora das 3 opções, não encerra. Pede novamente.
        await update.message.reply_text("Por favor, escolha um plano válido: Gratuito, Ouro ou Diamante.")
        return PLAN

async def payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Insira os dados do pagamento.")
    return ConversationHandler.END

async def exam(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Exame de sangue processado. Prescrição biodisponível gerada.")
    return RESULT

async def result(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Aqui está sua prescrição personalizada.")
    return ConversationHandler.END

# ---------------------------------------------------------------------
# Handler extra: Invalid plan ou fallback para o estado PLAN (se quiser separar)
# ---------------------------------------------------------------------
# Se quiser separar logicamente, você pode usar algo como:
# async def invalid_plan(update: Update, context: ContextTypes.DEFAULT_TYPE):
#     await update.message.reply_text("Por favor, escolha um plano válido: Gratuito, Ouro ou Diamante.")
#     return PLAN

# ---------------------------------------------------------------------
# Montagem do ConversationHandler
# ---------------------------------------------------------------------
conversation_handler = ConversationHandler(
    entry_points=[CommandHandler("start", welcome)],
    states={
        SYMPTOMS_YES_NO: [CallbackQueryHandler(symptoms_yes_no)],
        PLAN: [MessageHandler(filters.TEXT & (~filters.COMMAND), plan)],
        PAYMENT: [MessageHandler(filters.TEXT & (~filters.COMMAND), payment)],
        EXAM: [MessageHandler(filters.TEXT & (~filters.COMMAND), exam)],
        RESULT: [MessageHandler(filters.TEXT & (~filters.COMMAND), result)],
    },
    fallbacks=[CommandHandler("start", welcome)],
    per_message=True
)

# ---------------------------------------------------------------------
# Handler de Erros
# ---------------------------------------------------------------------
async def log_error(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Erro no update {update}: {context.error}")
    traceback.print_exc()

# ---------------------------------------------------------------------
# Setup do Webhook e Execução
# ---------------------------------------------------------------------
async def set_webhook():
    await telegram_app.bot.set_webhook(WEBHOOK_URL)
    logger.info(f"Webhook definido: {WEBHOOK_URL}")

async def main():
    telegram_app.add_handler(conversation_handler)
    telegram_app.add_error_handler(log_error)

    await set_webhook()

    await telegram_app.initialize()
    asyncio.create_task(telegram_app.start())

    asgi_app = WsgiToAsgi(app_flask)
    config = Config(
        app=asgi_app,
        host="0.0.0.0",
        port=int(os.getenv("PORT", "5000")),
        loop="asyncio",
        lifespan="off",
    )
    server = Server(config)

    logger.info("Iniciando Uvicorn + Bot no mesmo event loop ...")
    await server.serve()

    logger.info("Servidor Uvicorn parado. Encerrando bot.")
    await telegram_app.stop()

if __name__ == "__main__":
    asyncio.run(main())
