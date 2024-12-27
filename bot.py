import os
import asyncio
import logging
import traceback

from flask import Flask, request
from asgiref.wsgi import WsgiToAsgi
from uvicorn import Config, Server

from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardMarkup, InlineKeyboardButton
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

BOT_TOKEN = os.getenv("BOT_TOKEN", "YOUR_TOKEN_HERE")
RENDER_EXTERNAL_URL = os.getenv("RENDER_EXTERNAL_URL", "YOUR_URL_HERE")
WEBHOOK_PATH = f"/webhook/{BOT_TOKEN}"
WEBHOOK_URL = f"{RENDER_EXTERNAL_URL}{WEBHOOK_PATH}"

app_flask = Flask(__name__)
telegram_app = Application.builder().token(BOT_TOKEN).build()

@app_flask.route(WEBHOOK_PATH, methods=["POST"])
def webhook():
    """Rota SÍNCRONA do Flask para receber updates e colocar na fila."""
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

# --------------------------
# Estados e Handlers para o fluxo
# --------------------------
WELCOME, SYMPTOMS, ANALYZE, PLAN, PAYMENT, EXAM, RESULT, SYMPTOMS_YES_NO = range(8)

# Lista completa de sintomas
symptoms_list = [
    "Cansaço", "Falta de Apetite", "Dor de Cabeça",
    "Náusea", "Tontura", "Palpitações",
    "Falta de Energia", "Insônia"
]

plans_keyboard = [["Gratuito", "Ouro", "Diamante"]]

async def welcome(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["symptoms"] = []  # Inicializa a lista de sintomas
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
        await update.callback_query.edit_message_text("Nenhum sintoma selecionado. Por favor, reinicie o processo.")
        return ConversationHandler.END

    # Simulação de análise de carências
    deficiencies = {
        "Cansaço": "Possível deficiência de ferro ou vitamina B12",
        "Falta de Apetite": "Possível deficiência de zinco",
        "Dor de Cabeça": "Pode estar relacionada à desidratação ou falta de magnésio",
        "Tontura": "Possível deficiência de ferro",
        "Palpitações": "Pode indicar falta de potássio ou magnésio",
    }

    analysis_results = [deficiencies.get(symptom, "Sem análise disponível") for symptom in symptoms]
    results_text = "\n".join(f"- {symptom}: {result}" for symptom, result in zip(symptoms, analysis_results))

    await update.callback_query.edit_message_text(
        f"Baseado nos sintomas informados, aqui está a análise inicial:\n{results_text}"
    )
    await update.callback_query.message.reply_text(
        "Escolha um dos planos disponíveis para continuar.",
        reply_markup=ReplyKeyboardMarkup(plans_keyboard, one_time_keyboard=True, resize_keyboard=True)
    )
    return PLAN

async def plan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    plan_choice = update.message.text
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

async def payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Insira os dados do pagamento.")
    return ConversationHandler.END

async def exam(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Exame de sangue processado. Prescrição biodisponível gerada.")
    return RESULT

async def result(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Aqui está sua prescrição personalizada.")
    return ConversationHandler.END

# Adicionando os handlers ao ConversationHandler
conversation_handler = ConversationHandler(
    entry_points=[CommandHandler("start", welcome)],
    states={
        SYMPTOMS_YES_NO: [CallbackQueryHandler(symptoms_yes_no)],
        SYMPTOMS: [CallbackQueryHandler(symptoms)],
        ANALYZE: [MessageHandler(filters.TEXT, analyze)],
        PLAN: [MessageHandler(filters.TEXT, plan)],
        PAYMENT: [MessageHandler(filters.TEXT, payment)],
        EXAM: [MessageHandler(filters.TEXT, exam)],
        RESULT: [MessageHandler(filters.TEXT, result)],
    },
    fallbacks=[CommandHandler("start", welcome)]
)

# --------------------------
# Outros Handlers e Configuração do Bot
# --------------------------

async def log_error(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Erro no update {update}: {context.error}")
    traceback.print_exc()

async def set_webhook():
    await telegram_app.bot.set_webhook(WEBHOOK_URL)
    logger.info(f"Webhook definido: {WEBHOOK_URL}")

async def main():
    """
    Função principal que inicia:
      1) o PTB (Application) e seu loop interno
      2) o servidor Uvicorn, tudo no mesmo event loop
    """
    # 1. Registra handlers
    telegram_app.add_handler(conversation_handler)
    telegram_app.add_error_handler(log_error)

    # 2. Configura webhook
    await set_webhook()

    # 3. Inicializa o PTB
    await telegram_app.initialize()

    # 4. Inicia o PTB *em segundo plano*
    asyncio.create_task(telegram_app.start())

    # 5. Inicia o Uvicorn via Config+Server, sem usar uvicorn.run()
    asgi_app = WsgiToAsgi(app_flask)

    config = Config(
        app=asgi_app,
        host="0.0.0.0",
        port=int(os.getenv("PORT", "5000")),
        loop="asyncio",
        lifespan="off",
    )
    server = Server(config)

    # Uvicorn passa a rodar *no* loop atual
    logger.info("Iniciando Uvicorn + Bot no mesmo event loop ...")
    await server.serve()

    # Se o servidor encerrar, paramos o bot:
    logger.info("Servidor Uvicorn parado. Encerrando bot.")
    await telegram_app.stop()

if __name__ == "__main__":
    asyncio.run(main())
