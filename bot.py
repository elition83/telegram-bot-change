import logging
import os
import requests
from xml.etree import ElementTree as ET
from cachetools import TTLCache
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes

# Логирование
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Настройка кэша
cache = TTLCache(maxsize=10, ttl=18000)

# Хранилище заявок
user_requests = {}

# Поддерживаемые валюты
SUPPORTED_CURRENCIES = {
    "TRY": {"name": "Лира", "char_code": "TRY"},
    "RUB": {"name": "Рубль", "char_code": "RUB"},
    "USD": {"name": "Доллар", "char_code": "USD"},
    "EUR": {"name": "Евро", "char_code": "EUR"}
}

# Основная клавиатура
def get_main_keyboard():
    keyboard = [
        [InlineKeyboardButton("Текущий курс", callback_data="current_rate")],
        [InlineKeyboardButton("Подать заявку", callback_data="submit_request")],
    ]
    return InlineKeyboardMarkup(keyboard)

# Inline клавиатура выбора валют (с префиксом)
def get_currency_keyboard(prefix="rate_", exclude=None):
    currencies = SUPPORTED_CURRENCIES.copy()
    if exclude and exclude in currencies:
        currencies.pop(exclude)
    keyboard = [
        [InlineKeyboardButton(f"{data['name']} ({code})", callback_data=f"{prefix}{code}")]
        for code, data in currencies.items()
    ]
    return InlineKeyboardMarkup(keyboard)

# Получение курсов валют с сайта ЦБ РФ
def get_exchange_rate(base_currency: str) -> dict:
    if base_currency in cache:
        logger.info(f"Курс {base_currency} получен из кэша")
        return cache[base_currency]

    try:
        response = requests.get("https://www.cbr.ru/scripts/XML_daily.asp")
        response.raise_for_status()

        # Парсинг XML
        root = ET.fromstring(response.content)
        rates = {}
        base_rate = None
        base_nominal = 1

        # Чтение всех валют
        for currency in root.findall("Valute"):
            char_code = currency.find("CharCode").text
            value = float(currency.find("Value").text.replace(",", "."))
            nominal = int(currency.find("Nominal").text)

            if char_code == base_currency:
                base_rate = value
                base_nominal = nominal

            if char_code in SUPPORTED_CURRENCIES:
                rates[char_code] = value / nominal

        # Добавляем RUB как базовую валюту
        rates["RUB"] = 1.0

        # Если базовая валюта не RUB, пересчитываем курсы
        if base_currency != "RUB" and base_rate:
            for char_code in rates:
                rates[char_code] = (rates[char_code] / base_rate) * base_nominal

        cache[base_currency] = rates
        return rates

    except requests.RequestException as e:
        logger.error(f"Ошибка запроса к API ЦБ РФ: {e}")
    except ET.ParseError as e:
        logger.error(f"Ошибка парсинга XML: {e}")
    return {}

# Обработчик команды /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message:
        await update.message.reply_text("Убираю текущие клавиатуры...", reply_markup=ReplyKeyboardRemove())
        await update.message.reply_text("Привет! Выберите действие:", reply_markup=get_main_keyboard())
    elif update.callback_query:
        query = update.callback_query
        await query.message.reply_text("Привет! Выберите действие:", reply_markup=get_main_keyboard())

# Обработчик кнопки "Текущий курс"
async def current_rate(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "Выберите базовую валюту для отображения курсов:",
        reply_markup=get_currency_keyboard(prefix="rate_")
    )

# Обработчик выбора валюты (текущий курс)
async def handle_currency(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    if not query.data.startswith("rate_"):
        return

    base_currency = query.data.replace("rate_", "")
    rates = get_exchange_rate(base_currency)

    if rates:
        message = f"Курс валют относительно {SUPPORTED_CURRENCIES[base_currency]['name']} ({base_currency}):\n"
        for currency, rate in rates.items():
            if currency != base_currency:
                message += f"1 {base_currency} = {rate:.2f} {currency}\n"
    else:
        message = "Не удалось получить курсы валют. Попробуйте позже."

    # Отображаем курс
    await query.edit_message_text(text=message)

    # Возвращаемся на стартовое меню
    await start(update, context)

# Обработчик кнопки "Подать заявку"
async def submit_request(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    user_requests[user_id] = {}
    context.user_data['state'] = 'awaiting_from_currency'
    await query.edit_message_text(
        "Выберите валюту, которую хотите обменять:",
        reply_markup=get_currency_keyboard(prefix="req_")
    )

# Обработка подтверждения
async def handle_request_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query.data == "confirm_yes":
        await query.answer("Вы выбрали: Да.")
        await query.edit_message_text("Заявка успешно сохранена!")
    elif query.data == "confirm_no":
        await query.answer("Вы выбрали: Нет.")
        await query.edit_message_text("Заявка отменена.")

    # Возвращаемся на стартовое меню
    await start(update, context)

# Основная функция
def main() -> None:
    load_dotenv()
    token = os.getenv("TOKEN")
    if not token:
        logger.error("Переменная окружения TOKEN не установлена.")
        return

    application = Application.builder().token(token).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(current_rate, pattern="^current_rate$"))
    application.add_handler(CallbackQueryHandler(handle_currency, pattern="^rate_.*$"))
    application.add_handler(CallbackQueryHandler(submit_request, pattern="^submit_request$"))
    application.add_handler(CallbackQueryHandler(handle_request_confirmation, pattern="^confirm_.*$"))

    application.run_polling()

if __name__ == "__main__":
    main()
