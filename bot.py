import logging
import os
import requests
from cachetools import TTLCache
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, CallbackQueryHandler, filters

# Логирование
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

# Настройка кэша (максимум 10 записей, время жизни 5 часов = 18000 секунд)
cache = TTLCache(maxsize=10, ttl=18000)

# Постоянная клавиатура с кнопками
def get_main_keyboard():
    keyboard = [
        ["Текущий курс", "Заявки"],
        ["Подать заявку"]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

# Функция для получения курса валюты с использованием кэша
def get_exchange_rate(base_currency: str) -> dict:
    if base_currency in cache:
        return cache[base_currency]

    try:
        response = requests.get(f"https://open.er-api.com/v6/latest/{base_currency}")
        data = response.json()
        if data["result"] == "success":
            cache[base_currency] = data["rates"]  # Обновляем кэш для выбранной валюты
            return cache[base_currency]
        else:
            return {}
    except Exception as e:
        return {}

# Обработчик команды /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    await update.message.reply_html(
        rf"Привет, {user.mention_html()}!",
        reply_markup=get_main_keyboard(),  # Добавляем клавиатуру к сообщению
    )

# Обработчик для кнопки "Текущий курс"
async def current_rate(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("Выберите базовую валюту для курсов:", reply_markup=get_main_keyboard())

# Обработчик для кнопки "Заявки"
async def requests(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("Список заявок", reply_markup=get_main_keyboard())

# Обработчик для кнопки "Подать заявку"
async def submit_request(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("Введите данные для заявки", reply_markup=get_main_keyboard())

# Обработчик команды /rate для отображения кнопок с валютами
async def rate_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    keyboard = [
        [
            InlineKeyboardButton("Рубль (RUB)", callback_data='RUB'),
            InlineKeyboardButton("Доллар (USD)", callback_data='USD'),
            InlineKeyboardButton("Лира (TRY)", callback_data='TRY')
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Выберите базовую валюту:", reply_markup=reply_markup)

# Обработчик выбора валюты
async def button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    # Определение выбранной валюты как базовой
    base_currency = query.data

    # Получение курса валют относительно выбранной базовой валюты
    rates = get_exchange_rate(base_currency)

    # Формирование сообщения с курсами
    if rates:
        rate_message = (
            f"Курс валют относительно {base_currency}:\n"
            f"1 {base_currency} = {rates.get('USD', 'неизвестно')} USD\n"
            f"1 {base_currency} = {rates.get('RUB', 'неизвестно')} RUB\n"
            f"1 {base_currency} = {rates.get('TRY', 'неизвестно')} TRY\n"
        )
    else:
        rate_message = "Не удалось получить курс валют."

    # Отправка сообщения с курсом
    await query.edit_message_text(text=rate_message)

# Обработчик эхо сообщений
async def echo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(update.message.text)

def main() -> None:
    load_dotenv()

    token = os.getenv("TOKEN")
    if not token:
        logger.error("Переменная окружения TOKEN не установлена.")
        raise ValueError("Переменная окружения TOKEN не установлена")

    application = Application.builder().token(token).build()

    # Регистрируем обработчики команд
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("rate", rate_command))
    
    # Обработчик выбора валюты по нажатию кнопки
    application.add_handler(CallbackQueryHandler(button))

    # Обработчики сообщений с кнопками
    application.add_handler(MessageHandler(filters.Regex('^Текущий курс$'), current_rate))
    application.add_handler(MessageHandler(filters.Regex('^Заявки$'), requests))
    application.add_handler(MessageHandler(filters.Regex('^Подать заявку$'), submit_request))

    # Эхо-ответ на текстовые сообщения
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo))

    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
