import logging
import os
import requests
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
SUPPORTED_CURRENCIES = {"TRY": "Лира", "RUB": "Рубль", "USD": "Доллар", "EUR": "Евро"}

# Основная клавиатура
def get_main_keyboard():
	keyboard = [
		[InlineKeyboardButton("Текущий курс", callback_data="current_rate")],
		[InlineKeyboardButton("Подать заявку", callback_data="submit_request")],
	]
	return InlineKeyboardMarkup(keyboard)

# Inline клавиатура выбора валют
def get_currency_keyboard(exclude=None):
	currencies = SUPPORTED_CURRENCIES.copy()
	if exclude and exclude in currencies:
		currencies.pop(exclude)
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
			filtered_rates = {k: v for k, v in data["rates"].items() if k in SUPPORTED_CURRENCIES}
			cache[base_currency] = filtered_rates
			return filtered_rates
	except requests.RequestException as e:
		logger.error(f"Ошибка запроса к API: {e}")
	return {}

# Обработчик команды /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
	# Убираем текущие клавиатуры
	await update.message.reply_text("Убираю текущие клавиатуры...", reply_markup=ReplyKeyboardRemove())
	# Отправляем стандартное меню с основной клавиатурой
	await update.message.reply_text("Привет! Выберите действие:", reply_markup=get_main_keyboard())

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
		message = f"Курс валют относительно {SUPPORTED_CURRENCIES[base_currency]} ({base_currency}):\n"
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

# Обработка заявки (по этапам)
async def handle_request_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
	query = update.callback_query
	user_id = query.from_user.id
	text = query.data
	state = context.user_data.get('state')

	if not state:
		await query.edit_message_text("Неизвестное состояние. Попробуйте снова.", reply_markup=get_main_keyboard())
		return

	# Этап: выбор исходной валюты
	if state == 'awaiting_from_currency':
		user_requests[user_id]['from_currency'] = text
		context.user_data['state'] = 'awaiting_amount'  # Переход к этапу ввода суммы
		await query.edit_message_text(
			text="Введите сумму для обмена (например, 100):",
			reply_markup=None  # Удаляем Inline-клавиатуру
		)

	# Этап: выбор целевой валюты
	elif state == 'awaiting_to_currency':
		user_requests[user_id]['to_currency'] = text
		from_currency = user_requests[user_id]['from_currency']
		amount = user_requests[user_id]['amount']
		rates = get_exchange_rate(from_currency)

		if rates:
			exchange_rate = rates.get(text)
			if exchange_rate:
				converted_amount = amount * exchange_rate
				user_requests[user_id]['converted_amount'] = converted_amount
				context.user_data['state'] = 'awaiting_confirmation'  # Переход к этапу подтверждения
				await query.edit_message_text(
					f"Вы хотите обменять {amount} {from_currency} на {converted_amount:.2f} {text}. Подтвердить?",
					reply_markup=InlineKeyboardMarkup([
						[InlineKeyboardButton("Да", callback_data="confirm_yes")],
						[InlineKeyboardButton("Нет", callback_data="confirm_no")]
					])
				)
			else:
				await query.edit_message_text("Не удалось получить курс для выбранной валюты.")
		else:
			await query.edit_message_text("Не удалось получить курсы валют. Попробуйте позже.")

	# Этап: подтверждение заявки
	elif state == 'awaiting_confirmation':
		if text == "confirm_yes":
			logger.info(f"Заявка сохранена: {user_requests[user_id]}")
			context.user_data.pop('state', None)
			await query.edit_message_text("Заявка успешно сохранена!", reply_markup=get_main_keyboard())
		elif text == "confirm_no":
			context.user_data.pop('state', None)
			await query.edit_message_text("Заявка отменена.", reply_markup=get_main_keyboard())
			
# Обработка текста для этапа ввода суммы
async def handle_text_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
	user_id = update.effective_user.id
	text = update.message.text
	state = context.user_data.get('state')

	if state == 'awaiting_amount':
		try:
			amount = float(text)
			user_requests[user_id]['amount'] = amount
			context.user_data['state'] = 'awaiting_to_currency'
			from_currency = user_requests[user_id]['from_currency']
			await update.message.reply_text(
				"Выберите валюту, на которую хотите обменять:",
				reply_markup=get_currency_keyboard(exclude=from_currency)
			)
		except ValueError:
			await update.message.reply_text("Введите корректное число:")

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
	application.add_handler(CallbackQueryHandler(handle_request_input, pattern="^(TRY|RUB|USD|EUR|confirm_yes|confirm_no)$"))
	application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_input))

	application.run_polling()

if __name__ == "__main__":
	main()
