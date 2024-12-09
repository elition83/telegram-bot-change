import logging
import os
import requests
from cachetools import TTLCache
from dotenv import load_dotenv
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

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
			cache[base_currency] = data["rates"]
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

# Обработчик команды /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
	await update.message.reply_text(
		"Привет! Выберите действие:",
		reply_markup=get_main_keyboard()
	)

# Обработчик кнопки "Подать заявку"
async def submit_request(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
	user_id = update.effective_user.id
	user_requests[user_id] = {}  # Инициализируем заявку
	context.user_data['state'] = 'awaiting_from_currency'

	await update.message.reply_text(
		"Какую валюту вы хотите поменять?",
		reply_markup=ReplyKeyboardMarkup([["Лира", "Рубль", "Доллар", "Евро"], ["Отмена"]], resize_keyboard=True)
	)

# Обработчик ввода данных заявки
async def handle_request_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
	user_id = update.effective_user.id
	text = update.message.text
	state = context.user_data.get('state')

	if state == 'awaiting_from_currency':
		if text.lower() == "отмена":
			await update.message.reply_text("Подача заявки отменена.", reply_markup=get_main_keyboard())
			context.user_data.pop('state', None)
			return

		valid_currencies = ["Лира", "Рубль", "Доллар", "Евро"]
		if text in valid_currencies:
			user_requests[user_id]['from_currency'] = text
			context.user_data['state'] = 'awaiting_amount'
			await update.message.reply_text("Введите сумму для обмена:", reply_markup=ReplyKeyboardMarkup([["Отмена"]], resize_keyboard=True))
		else:
			await update.message.reply_text("Выберите корректную валюту.")

	elif state == 'awaiting_amount':
		if text.lower() == "отмена":
			await update.message.reply_text("Подача заявки отменена.", reply_markup=get_main_keyboard())
			context.user_data.pop('state', None)
			return

		try:
			amount = float(text)
			user_requests[user_id]['amount'] = amount
			context.user_data['state'] = 'awaiting_to_currency'
			await update.message.reply_text(
				"На какую валюту вы хотите обменять?",
				reply_markup=ReplyKeyboardMarkup([["Лира", "Рубль", "Доллар", "Евро"], ["Отмена"]], resize_keyboard=True)
			)
		except ValueError:
			await update.message.reply_text("Введите корректное число.")

	elif state == 'awaiting_to_currency':
		if text.lower() == "отмена":
			await update.message.reply_text("Подача заявки отменена.", reply_markup=get_main_keyboard())
			context.user_data.pop('state', None)
			return

		valid_currencies = ["Лира", "Рубль", "Доллар", "Евро"]
		if text in valid_currencies:
			user_requests[user_id]['to_currency'] = text
			context.user_data.pop('state', None)

			# Получаем курсы валют и производим расчёт
			from_currency = user_requests[user_id]['from_currency']
			to_currency = text
			amount = user_requests[user_id]['amount']
			rates = get_exchange_rate(from_currency)

			if rates:
				exchange_rate = rates.get(to_currency.upper(), None)
				if exchange_rate:
					converted_amount = amount * exchange_rate
					await update.message.reply_text(
						f"Вы хотите обменять {amount} {from_currency} на {converted_amount:.2f} {to_currency}.",
						reply_markup=get_main_keyboard()
					)
				else:
					await update.message.reply_text("Не удалось получить курс для выбранной валюты.")
			else:
				await update.message.reply_text("Не удалось получить курсы валют. Попробуйте позже.")
		else:
			await update.message.reply_text("Выберите корректную валюту.")

	else:
		await update.message.reply_text("Неизвестное состояние. Попробуйте снова.", reply_markup=get_main_keyboard())

# Основная функция
def main() -> None:
	load_dotenv()
	token = os.getenv("TOKEN")
	if not token:
		logger.error("Переменная окружения TOKEN не установлена.")
		return

	application = Application.builder().token(token).build()

	application.add_handler(CommandHandler("start", start))
	application.add_handler(MessageHandler(filters.Regex("^Подать заявку$"), submit_request))
	application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_request_input))

	application.run_polling()

if __name__ == "__main__":
	main()
