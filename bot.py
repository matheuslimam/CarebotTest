import os
import asyncio
import logging
import traceback

from flask import Flask, request
from asgiref.wsgi import WsgiToAsgi
from uvicorn import Config, Server

from telegram import (
    Update,
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

BOT_TOKEN = os.getenv("BOT_TOKEN", "YOUR_TOKEN_HERE")
RENDER_EXTERNAL_URL = os.getenv("RENDER_EXTERNAL_URL", "YOUR_URL_HERE")
WEBHOOK_PATH = f"/webhook/{BOT_TOKEN}"
WEBHOOK_URL = f"{RENDER_EXTERNAL_URL}{WEBHOOK_PATH}"

app_flask = Flask(__name__)
telegram_app = Application.builder().token(BOT_TOKEN).build()

@app_flask.route(WEBHOOK_PATH, methods=["POST"])
def webhook():
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

# Definição de estados
WELCOME, SYMPTOMS, ANALYZE, PLAN, PAYMENT, EXAM, RESULT, SYMPTOMS_YES_NO = range(8)

symptoms_list = [
    "Cansaço", "Falta de Apetite", "Dor de Cabeça",
    "Náusea", "Tontura", "Palpitações",
    "Falta de Energia", "Insônia"
]

async def welcome(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["symptoms"] = []
    context.user_data["current_symptom_index"] = 0
    await send_yes_no_question(update, context)
    return SYMPTOMS_YES_NO

async def send_yes_no_question(update: Update, context: ContextTypes.DEFAULT_TYPE):
    index = context.user_data.get("current_symptom_index", 0)
    if index >= len(symptoms_list):
        # Se já perguntamos todos os sintomas, vamos para a análise
        return await analyze(update, context)

    symptom = symptoms_list[index]
    keyboard = [
        [
            InlineKeyboardButton("Sim", callback_data="yes"),
            InlineKeyboardButton("Não", callback_data="no")
        ]
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
    return await send_yes_no_question(update, context)

async def analyze(update: Update, context: ContextTypes.DEFAULT_TYPE):
    symptoms = context.user_data.get("symptoms", [])
    if not symptoms:
        await update.callback_query.edit_message_text(
            "Nenhum sintoma selecionado. Por favor, reinicie o processo."
        )
        return ConversationHandler.END

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
        f"- {symptom}: {result}"
        for symptom, result in zip(symptoms, analysis_results)
    )

    # Editar a mensagem de análise
    await update.callback_query.edit_message_text(
        text=(
            f"Baseado nos sintomas informados, aqui está a análise inicial:\n"
            f"{results_text}"
        )
    )

    # Enviar nova mensagem com inline keyboard para planos
    inline_plans_keyboard = [
        [
            InlineKeyboardButton("Gratuito", callback_data="plan_gratuito"),
            InlineKeyboardButton("Ouro", callback_data="plan_ouro"),
            InlineKeyboardButton("Diamante", callback_data="plan_diamante"),
        ]
    ]
    await telegram_app.bot.send_message(
        chat_id=update.callback_query.message.chat_id,
        text="Escolha um dos planos disponíveis para continuar:",
        reply_markup=InlineKeyboardMarkup(inline_plans_keyboard),
    )

    return PLAN

async def plan_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    plan_choice = query.data  # "plan_gratuito", "plan_ouro" ou "plan_diamante"

    if plan_choice == "plan_gratuito":
        context.user_data["plan"] = "Gratuito"
        await query.edit_message_text(
            "Aqui está uma prévia da sua prescrição básica."
        )
        return ConversationHandler.END

    elif plan_choice == "plan_ouro":
        context.user_data["plan"] = "Ouro"
        await query.edit_message_text(
            "Você escolheu o plano Ouro. Por favor, realize o pagamento."
        )
        # Vamos direto para a etapa de pagamento
        return PAYMENT

    elif plan_choice == "plan_diamante":
        context.user_data["plan"] = "Diamante"
        await query.edit_message_text(
            "Você escolheu o plano Diamante. Por favor, realize o pagamento."
        )
        # Vamos direto para a etapa de pagamento
        return PAYMENT

    await query.edit_message_text("Plano não reconhecido. Por favor, tente novamente.")
    return PLAN

async def payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Assim que o pagamento for “recebido”, decidimos o próximo passo:
    - Se for Ouro, podemos encerrar logo após confirmar.
    - Se for Diamante, pedimos para enviar o exame de sangue.
    """
    plan = context.user_data.get("plan", "Desconhecido")

    # Exemplos de tratativa de pagamento
    user_message = update.message.text
    logger.info(f"Usuário enviou: {user_message} (para pagamento do plano {plan})")

    # Resposta padrão
    await update.message.reply_text("Pagamento recebido com sucesso!")

    if plan == "Diamante":
        # Agora solicitamos o exame
        await update.message.reply_text(
            "Envie o resultado do exame de sangue para prosseguirmos."
        )
        return EXAM
    else:
        # Se for Ouro (ou algum outro que você queira encerrar)
        await update.message.reply_text(
            f"Você concluiu o pagamento do Plano {plan}. Aqui está a sua prescrição!"
        )
        return ConversationHandler.END

async def exam(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Lógica para tratar o recebimento do exame no plano Diamante,
    podendo depois gerar a prescrição e encerrar.
    """
    # Exemplo: o usuário envia alguma informação que chamamos de "exame"
    exam_result = update.message.text
    logger.info(f"Exame recebido: {exam_result}")

    await update.message.reply_text(
        "Exame de sangue processado com sucesso. Aqui está a sua prescrição personalizada!"
    )
    return ConversationHandler.END

async def result(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Aqui está sua prescrição personalizada.")
    return ConversationHandler.END

async def log_error(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Erro no update {update}: {context.error}")
    traceback.print_exc()

conversation_handler = ConversationHandler(
    entry_points=[CommandHandler("start", welcome)],
    states={
        SYMPTOMS_YES_NO: [CallbackQueryHandler(symptoms_yes_no)],
        PLAN: [CallbackQueryHandler(plan_callback, pattern="^plan_")],
        PAYMENT: [MessageHandler(filters.TEXT & (~filters.COMMAND), payment)],
        EXAM: [MessageHandler(filters.TEXT & (~filters.COMMAND), exam)],
        RESULT: [MessageHandler(filters.TEXT & (~filters.COMMAND), result)],
    },
    fallbacks=[CommandHandler("start", welcome)]
)

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
