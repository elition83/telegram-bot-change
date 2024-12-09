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

# Настройка кэша
cache = TTLCache(maxsize=10, ttl=18000)

# Хранилище заявок
user_requests = {}

# Основная клавиатура
def get_main_keyboard():
	keyboard = [
		[InlineKeyboardButton("Текущий курс", callback_data="current_rate")],
		[InlineKeyboardButton("Подать заявку", callback_data="submit_request")],
	]
	return InlineKeyboardMarkup(keyboard)

# Inline клавиатура выбора валют
def get_currency_keyboard(exclude=None):
	currencies = {"TRY": "Лира", "RUB": "Рубль", "USD": "Доллар", "EUR": "Евро"}
	if exclude:
		currencies.pop(exclude, None)
	keyboard = [[InlineKeyboardButton(f"{name} ({code})", callback_data=code)] for code, name in currencies.items()]
	return InlineKeyboardMarkup(keyboard)

# Получение курсов валют
def get_exchange_rate(base_currency: str) -> dict:
	if base_currency in cache:
		logger.info(f"Курс {base_currency} получен из кэша")
		return cache[base_currency]

	try:
		response = requests.get(f"https://open.er-api.com/v6/latest/{base_currency}")
		response.raise_for_status()
		data = response.json()
		if data.get("result") == "success" and data.get("rates"):
			cache[base_currency] = data["rates"]
			return data["rates"]
		else:
			logger.error(f"Ошибка API: {data}")
			return {}
	except requests.RequestException as e:
		logger.error(f"Ошибка запроса к API: {e}")
		return {}

# Обработчик команды /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
	await update.message.reply_text(
		"Привет! Выберите действие:",
		reply_markup=get_main_keyboard()
	)

# Обработчик кнопки "Текущий курс"
async def current_rate(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
	query = update.callback_query
	await query.answer()
	await query.edit_message_text(
		"Выберите базовую валюту для отображения курсов:",
		reply_markup=get_currency_keyboard()
	)

# Обработчик выбора валюты (курсы)
async def handle_currency(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
	query = update.callback_query
	await query.answer()

	base_currency = query.data
	rates = get_exchange_rate(base_currency)

	if rates:
		message = f"Курс валют относительно {base_currency}:\n"
		for currency, rate in rates.items():
			if currency != base_currency:
				message += f"1 {base_currency} = {rate:.2f} {currency}\n"
	else:
		message = "Не удалось получить курсы валют. Попробуйте позже."

	await query.edit_message_text(text=message)

# Обработчик кнопки "Подать заявку"
async def submit_request(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
	query = update.callback_query
	await query.answer()
	user_id = query.from_user.id
	user_requests[user_id] = {}
	context.user_data['state'] = 'awaiting_from_currency'
	await query.edit_message_text(
		"Выберите валюту, которую хотите обменять:",
		reply_markup=get_currency_keyboard()
	)

# Обработка заявки (через InlineKeyboardMarkup)
async def handle_request_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
	query = update.callback_query
	await query.answer()
	user_id = query.from_user.id
	text = query.data
	state = context.user_data.get('state')

	if state == 'awaiting_from_currency':
		user_requests[user_id]['from_currency'] = text
		context.user_data['state'] = 'awaiting_amount'
		await query.edit_message_text("Введите сумму для обмена (например, 100):")
	elif state == 'awaiting_amount':
		try:
			amount = float(text)
			user_requests[user_id]['amount'] = amount
			context.user_data['state'] = 'awaiting_to_currency'
			from_currency = user_requests[user_id]['from_currency']
			await query.edit_message_text(
				"Выберите валюту, на которую хотите обменять:",
				reply_markup=get_currency_keyboard(exclude=from_currency)
			)
		except ValueError:
			await query.edit_message_text("Введите корректное число:")
	elif state == 'awaiting_to_currency':
		to_currency = text
		from_currency = user_requests[user_id]['from_currency']
		amount = user_requests[user_id]['amount']
		rates = get_exchange_rate(from_currency)

		if rates:
			exchange_rate = rates.get(to_currency)
			if exchange_rate:
				converted_amount = amount * exchange_rate
				await query.edit_message_text(
					f"Вы хотите обменять {amount} {from_currency} на {converted_amount:.2f} {to_currency}.",
					reply_markup=get_main_keyboard()
				)
			else:
				await query.edit_message_text("Не удалось получить курс для выбранной валюты.")
		else:
			await query.edit_message_text("Не удалось получить курсы валют. Попробуйте позже.")
		context.user_data.pop('state', None)

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
	application.add_handler(CallbackQueryHandler(handle_currency, pattern="^(TRY|RUB|USD|EUR)$"))
	application.add_handler(CallbackQueryHandler(submit_request, pattern="^submit_request$"))
	application.add_handler(CallbackQueryHandler(handle_request_input))

	application.run_polling()

if __name__ == "__main__":
	main()
