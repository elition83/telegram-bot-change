import logging
import os
import requests
from cachetools import TTLCache
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters

# Хранилище для заявок (в памяти, можно заменить на базу данных)
user_requests = {}

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

# Основная клавиатура
def get_main_keyboard():
	keyboard = [
		["Текущий курс", "Подать заявку"],
		["Мои заявки"]
	]
	return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

# Inline-клавиатура для выбора валюты
def get_currency_keyboard():
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
	return InlineKeyboardMarkup(keyboard)

# Обработчик команды /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
	user = update.effective_user
	await update.message.reply_text(
		f"Привет, {user.mention_html()}! Выберите действие:",
		reply_markup=get_main_keyboard(),
		parse_mode="HTML"
	)

# Обработчик кнопки "Текущий курс"
async def current_rate(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
	await update.message.reply_text(
		"Выберите базовую валюту для отображения курсов:",
		reply_markup=get_currency_keyboard()
	)

# Обработчик выбора валюты
async def handle_currency(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
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
		rate_message = "Не удалось получить курсы валют. Попробуйте позже."

	await query.edit_message_text(text=rate_message)

# Обработчик кнопки "Подать заявку"
async def submit_request(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
	user_id = update.effective_user.id
	user_requests[user_id] = {}  # Создаём пустой объект для хранения данных заявки

	await update.message.reply_text(
		"Введите имя:",
		reply_markup=ReplyKeyboardMarkup([["Отмена"]], resize_keyboard=True)
	)
	context.user_data['state'] = 'awaiting_name'  # Устанавливаем состояние для обработки имени

# Обработчик текстового ввода данных для заявки
async def handle_request_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
	user_id = update.effective_user.id
	text = update.message.text

	# Проверка состояния
	state = context.user_data.get('state')

	if state == 'awaiting_name':
		if text.lower() == "отмена":
			await update.message.reply_text("Подача заявки отменена.", reply_markup=get_main_keyboard())
			context.user_data.pop('state', None)  # Сброс состояния
			return

		# Сохраняем имя и переходим к следующему шагу
		user_requests[user_id]['name'] = text
		context.user_data['state'] = 'awaiting_amount'
		await update.message.reply_text("Введите сумму для обмена:", reply_markup=ReplyKeyboardMarkup([["Отмена"]], resize_keyboard=True))

	elif state == 'awaiting_amount':
		if text.lower() == "отмена":
			await update.message.reply_text("Подача заявки отменена.", reply_markup=get_main_keyboard())
			context.user_data.pop('state', None)  # Сброс состояния
			return

		# Проверяем, является ли введённое значение числом
		try:
			amount = float(text)
			user_requests[user_id]['amount'] = amount
			context.user_data['state'] = 'awaiting_currency'
			await update.message.reply_text(
				"Выберите валюту для обмена:",
				reply_markup=ReplyKeyboardMarkup([["Лира", "Рубль", "Доллар", "Евро"], ["Отмена"]], resize_keyboard=True)
			)
		except ValueError:
			await update.message.reply_text("Введите корректную сумму.")

	elif state == 'awaiting_currency':
		if text.lower() == "отмена":
			await update.message.reply_text("Подача заявки отменена.", reply_markup=get_main_keyboard())
			context.user_data.pop('state', None)  # Сброс состояния
			return

		valid_currencies = ["Лира", "Рубль", "Доллар", "Евро"]
		if text in valid_currencies:
			user_requests[user_id]['currency'] = text
			context.user_data.pop('state', None)  # Завершаем сбор данных

			# Подтверждаем успешную подачу заявки
			await update.message.reply_text(
				f"Заявка успешно подана:\n"
				f"Имя: {user_requests[user_id]['name']}\n"
				f"Сумма: {user_requests[user_id]['amount']}\n"
				f"Валюта: {user_requests[user_id]['currency']}\n",
				reply_markup=get_main_keyboard()
			)
		else:
			await update.message.reply_text("Выберите одну из предложенных валют.")

	else:
		await update.message.reply_text("Неизвестное состояние. Попробуйте снова.", reply_markup=get_main_keyboard())

# Обработчик кнопки "Мои заявки"
async def my_requests(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
	await update.message.reply_text(
		"Здесь будут отображаться ваши заявки.",
		reply_markup=get_main_keyboard()
	)

# Обработчик текстовых сообщений (если ничего не подходит)
async def echo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
	await update.message.reply_text("Команда не распознана. Используйте кнопки для действий.")

def main() -> None:
	load_dotenv()

	token = os.getenv("TOKEN")
	if not token:
		logger.error("Переменная окружения TOKEN не установлена.")
		raise ValueError("Переменная окружения TOKEN не установлена")

	application = Application.builder().token(token).build()

	# Регистрация обработчиков
	application.add_handler(CommandHandler("start", start))
	application.add_handler(MessageHandler(filters.Regex("^Текущий курс$"), current_rate))
	application.add_handler(MessageHandler(filters.TEXT & filters.Regex("^Подать заявку$"), submit_request))
	application.add_handler(CallbackQueryHandler(handle_currency, pattern="^(EUR|USD|RUB|TRY)$"))
	application.add_handler(MessageHandler(filters.Regex("^Мои заявки$"), my_requests))
	application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo))
	application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_request_input))

	# Запуск бота
	application.run_polling()

if __name__ == "__main__":
	main()
