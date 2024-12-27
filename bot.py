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
    InlineKeyboardButton,
    LabeledPrice,
    ShippingOption,
    PreCheckoutQuery,
    SuccessfulPayment
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes,
    ConversationHandler,
    PreCheckoutQueryHandler,
    ShippingQueryHandler
)

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN", "YOUR_TOKEN_HERE")
RENDER_EXTERNAL_URL = os.getenv("RENDER_EXTERNAL_URL", "YOUR_URL_HERE")
WEBHOOK_PATH = f"/webhook/{BOT_TOKEN}"
WEBHOOK_URL = f"{RENDER_EXTERNAL_URL}{WEBHOOK_PATH}"

# 1) TOKEN do provedor de pagamento oficial do Telegram (obtido no BotFather)
PAYMENT_PROVIDER_TOKEN = os.getenv("PAYMENT_PROVIDER_TOKEN", "PROVIDER_TOKEN_AQUI")

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
    context.user_data["plan"] = plan_choice

    if plan_choice == "plan_gratuito":
        await query.edit_message_text(
            "Aqui está uma prévia da sua prescrição básica."
        )
        return ConversationHandler.END
    elif plan_choice in ["plan_ouro", "plan_diamante"]:
        # Chamamos a função que envia a invoice
        await query.edit_message_text(
            f"Você escolheu o plano {plan_choice.replace('plan_', '').capitalize()}.\nEnviando a invoice de pagamento..."
        )
        await send_invoice(update, context)
        # Fica aguardando a conclusão do pagamento
        return PAYMENT

    await query.edit_message_text("Plano não reconhecido. Por favor, tente novamente.")
    return PLAN

# ------------------------------------------------------------------------------
# 2) FUNÇÃO PARA ENVIAR A INVOICE VIA TELEGRAM
# ------------------------------------------------------------------------------
async def send_invoice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Envia a Invoice de acordo com o plano escolhido."""
    chat_id = update.callback_query.message.chat_id
    plan = context.user_data.get("plan", "desconhecido")

    if plan == "plan_ouro":
        title = "Plano Ouro"
        description = "Pagamento do Plano Ouro"
        prices = [LabeledPrice("Plano Ouro", 50000)]  # valor em centavos. Ex: R$500,00
    elif plan == "plan_diamante":
        title = "Plano Diamante"
        description = "Pagamento do Plano Diamante"
        prices = [LabeledPrice("Plano Diamante", 100000)]  # Ex: R$1000,00
    else:
        # fallback
        title = "Plano Desconhecido"
        description = "Valor genérico"
        prices = [LabeledPrice("Pagamento Genérico", 10000)]  # R$100

    payload = f"{plan}_payload_123"  # algo para identificar internamente
    currency = "BRL"

    # Enviando invoice:
    await telegram_app.bot.send_invoice(
        chat_id,
        title=title,
        description=description,
        payload=payload,
        provider_token=PAYMENT_PROVIDER_TOKEN,  # TOKEN do provedor
        currency=currency,
        prices=prices,
        # Se NÃO precisa de endereço de envio, definimos:
        need_name=True,
        need_phone_number=False,
        need_shipping_address=False,
        is_flexible=False,  # se tiver frete variado, vira True
    )

# ------------------------------------------------------------------------------
# 3) TRATANDO A CONFIRMAÇÃO (PreCheckoutQuery) E O PAGAMENTO CONCLUÍDO
# ------------------------------------------------------------------------------
async def precheckout_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Chamado antes de finalizar a compra. Validamos e respondemos se está ok."""
    query: PreCheckoutQuery = update.pre_checkout_query
    # Se quiser, pode checar algo no payload
    if not query.invoice_payload:
        # se algo estiver errado, responda com ok=False e reason
        await query.answer(ok=False, error_message="Falha ao processar pagamento.")
    else:
        await query.answer(ok=True)

async def successful_payment_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Quando o pagamento é concluído com sucesso, o Telegram envia no 'message.successful_payment'.
    """
    payment: SuccessfulPayment = update.message.successful_payment
    logger.info(f"Pagamento bem-sucedido. Detalhes: {payment.to_dict()}")

    plan = context.user_data.get("plan", "Desconhecido")

    # Resposta ao usuário
    await update.message.reply_text(
        f"Pagamento do {plan.replace('plan_', '').capitalize()} confirmado com sucesso!\n"
        "Obrigado. Agora prossiga com o que for necessário."
    )

    if plan == "plan_diamante":
        # Pedir envio de exame
        await update.message.reply_text(
            "Envie o resultado do exame de sangue para prosseguirmos."
        )
        return EXAM
    elif plan == "plan_ouro":
        # Encerrar (ou mostrar prescrição)
        await update.message.reply_text("Aqui está a sua prescrição do Plano Ouro!")
        return ConversationHandler.END

    # Caso não seja nenhum dos dois, encerra:
    return ConversationHandler.END


# ------------------------------------------------------------------------------
# 4) TRATANDO CASO SEJA EXIGIDO EXAME (DIAMANTE)
# ------------------------------------------------------------------------------
async def exam(update: Update, context: ContextTypes.DEFAULT_TYPE):
    exam_result = update.message.text
    logger.info(f"Exame recebido: {exam_result}")

    await update.message.reply_text(
        "Exame de sangue processado. Aqui está sua prescrição personalizada!"
    )
    return ConversationHandler.END


# ------------------------------------------------------------------------------
# 5) (Opcional) Se quiser tratar envio físico, use ShippingQueryHandler:
# ------------------------------------------------------------------------------
async def shipping_query_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Exemplo caso seu produto exija envio (need_shipping_address=True).
    Precisaria definir shipping_options.
    """
    shipping_query = update.shipping_query
    shipping_options = [
        ShippingOption(
            id="frete_normal",
            title="Frete Normal",
            prices=[LabeledPrice("Frete Normal", 1000)]
        ),
        ShippingOption(
            id="frete_express",
            title="Frete Expresso",
            prices=[LabeledPrice("Frete Expresso", 2000)]
        )
    ]
    await shipping_query.answer(ok=True, shipping_options=shipping_options)


async def result(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Aqui está sua prescrição personalizada.")
    return ConversationHandler.END


async def log_error(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Erro no update {update}: {context.error}")
    traceback.print_exc()


# ------------------------------------------------------------------------------
# 6) CONFIGURANDO OS HANDLERS E ESTADOS DA CONVERSATION
# ------------------------------------------------------------------------------
conversation_handler = ConversationHandler(
    entry_points=[CommandHandler("start", welcome)],
    states={
        SYMPTOMS_YES_NO: [CallbackQueryHandler(symptoms_yes_no)],
        PLAN: [CallbackQueryHandler(plan_callback, pattern="^plan_")],

        # Quando enviamos a invoice, ficamos no estado PAYMENT. O pagamento oficial
        # não é processado via 'message' de texto, mas via PreCheckout e successful_payment.
        # Então aqui, se o usuário mandar algo antes do pagamento oficial, ainda estamos no PAYMENT.
        PAYMENT: [
            MessageHandler(filters.TEXT & (~filters.COMMAND), lambda u, c: c.bot.send_message(
                u.message.chat_id, "Aguarde o fluxo de pagamento oficial!")
            )
        ],

        EXAM: [MessageHandler(filters.TEXT & (~filters.COMMAND), exam)],
        RESULT: [MessageHandler(filters.TEXT & (~filters.COMMAND), result)],
    },
    fallbacks=[CommandHandler("start", welcome)]
)

# ------------------------------------------------------------------------------
# 7) FUNÇÃO PRINCIPAL E WEBHOOK
# ------------------------------------------------------------------------------
async def set_webhook():
    await telegram_app.bot.set_webhook(WEBHOOK_URL)
    logger.info(f"Webhook definido: {WEBHOOK_URL}")


async def main():
    # Adicionamos o conversation handler
    telegram_app.add_handler(conversation_handler)

    # 7.1) Adicionamos handler para PreCheckout
    telegram_app.add_handler(PreCheckoutQueryHandler(precheckout_callback))

    # 7.2) Adicionamos handler para pagamento bem-sucedido
    #     Basta verificar se a mensagem possui successful_payment
    from telegram.ext.filters import StatusUpdate
    telegram_app.add_handler(
        MessageHandler(
            StatusUpdate.SUCCESSFUL_PAYMENT,
            successful_payment_callback
        )
    )

    # 7.3) Se precisar do shipping, adicionamos:
    telegram_app.add_handler(ShippingQueryHandler(shipping_query_handler))

    # 7.4) Handler global de erros
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
