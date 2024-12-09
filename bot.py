import logging
import os
import requests
from cachetools import TTLCache
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

# Логирование
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Настройка кэша (максимум 10 записей, время жизни 5 часов = 18000 секунд)
cache = TTLCache(maxsize=10, ttl=18000)

# Функция для получения курса валюты с использованием кэша
def get_exchange_rate(base_currency: str) -> dict:
    if base_currency in cache:
        logger.info(f"Курс {base_currency} получен из кэша")
        return cache[base_currency]

    try:
        response = requests.get(f"https://open.er-api.com/v6/latest/{base_currency}")
        response.raise_for_status()
        data = response.json()

        if data.get("result") == "success" and data.get("rates"):
            cache[base_currency] = data["rates"]  # Сохраняем данные в кэш
            logger.info(f"Курс {base_currency} обновлён в кэше")
            return data["rates"]
        else:
            logger.error(f"Ошибка при получении курса: {data}")
            return {}
    except requests.RequestException as e:
        logger.error(f"Ошибка запроса к API: {e}")
        return {}

# Обработчик команды /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    keyboard = [
        [InlineKeyboardButton("Текущий курс", callback_data="current_rate")],
        [InlineKeyboardButton("Подать заявку на обмен", callback_data="submit_request")],
        [InlineKeyboardButton("Мои заявки", callback_data="my_requests")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "Привет! Выберите действие:", reply_markup=reply_markup
    )

# Обработчик выбора действия
async def handle_action(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    action = query.data
    if action == "current_rate":
        # Предлагаем выбор валют
        keyboard = [
            [
                InlineKeyboardButton("Лира (TRY)", callback_data="TRY"),
                InlineKeyboardButton("Рубль (RUB)", callback_data="RUB"),
            ],
            [
                InlineKeyboardButton("Доллар (USD)", callback_data="USD"),
                InlineKeyboardButton("Евро (EUR)", callback_data="EUR"),
            ],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            "Выберите базовую валюту для отображения курсов:", reply_markup=reply_markup
        )
    elif action == "submit_request":
        await query.edit_message_text("Функция подачи заявки пока не реализована.")
    elif action == "my_requests":
        await query.edit_message_text("Здесь будут отображаться ваши заявки.")
    else:
        await query.edit_message_text("Неизвестное действие. Попробуйте снова.")

# Обработчик выбора валюты
async def show_rates(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    base_currency = query.data
    rates = get_exchange_rate(base_currency)

    if rates:
        rate_message = (
            f"Курс валют относительно {base_currency}:\n"
            f"1 {base_currency} = {rates.get('EUR', 'данные отсутствуют')} EUR\n"
            f"1 {base_currency} = {rates.get('USD', 'данные отсутствуют')} USD\n"
            f"1 {base_currency} = {rates.get('RUB', 'данные отсутствуют')} RUB\n"
            f"1 {base_currency} = {rates.get('TRY', 'данные отсутствуют')} TRY\n"
        )
    else:
        rate_message = "Не удалось получить курсы валют. Пожалуйста, повторите попытку позже."

    await query.edit_message_text(text=rate_message)

def main() -> None:
    load_dotenv()

    token = os.getenv("TOKEN")
    if not token:
        logger.error("Переменная окружения TOKEN не установлена.")
        raise ValueError("Переменная окружения TOKEN не установлена")

    application = Application.builder().token(token).build()

    # Регистрация обработчиков
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(handle_action, pattern="^(current_rate|submit_request|my_requests)$"))
    application.add_handler(CallbackQueryHandler(show_rates, pattern="^(EUR|USD|RUB|TRY)$"))

    # Запуск бота
    application.run_polling()

if __name__ == "__main__":
    main()
