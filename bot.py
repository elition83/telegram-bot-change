
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

def format_number(value: float) -> str:
    if value >= 1:
        # Для чисел >= 1 оставляем два знака после запятой
        return f"{value:.2f}"
    else:
        # Для чисел < 1 оставляем три значащие цифры после ведущих нулей
        fractional_part = f"{value:.10f}".split(".")[1]
        leading_zeros = len(fractional_part) - len(fractional_part.lstrip("0"))
        return "0." + "0" * leading_zeros + fractional_part.lstrip("0")[:3]

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

		# Чтение всех валют
		for currency in root.findall("Valute"):
			char_code = currency.find("CharCode").text

			# Проверяем, интересует ли нас эта валюта
			if char_code in SUPPORTED_CURRENCIES:
				vunit_rate = float(currency.find("VunitRate").text.replace(",", "."))

				# Сохраняем VunitRate для каждой валюты
				rates[char_code] = vunit_rate

				# Определяем VunitRate базовой валюты
				if char_code == base_currency:
					base_rate = vunit_rate

		# Добавляем RUB как базовую валюту
		rates["RUB"] = 1.0

		# Если базовая валюта не RUB, пересчитываем курсы
		if base_currency != "RUB" and base_rate:
			for char_code in rates:
				rates[char_code] = base_rate / rates[char_code]

		# Кэшируем результат
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
		# Отправляем новое сообщение
		await update.message.reply_text(
			"Привет! Выберите действие:", reply_markup=get_main_keyboard()
		)
	elif update.callback_query:
		query = update.callback_query
		await query.answer()  # Обязательно завершаем callback
		# Отправляем новое сообщение вместо редактирования
		await query.message.reply_text(
			"Привет! Выберите действие:", reply_markup=get_main_keyboard()
		)

# Обработчик команды /calc
async def calc(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    user_calculator[user_id] = {"input": "", "base_currency": None}

    await update.message.reply_text(
        "Введите сумму с помощью кнопок ниже и нажмите ✅ Рассчитать:",
        reply_markup=get_calculator_keyboard()
    )

Генерация клавиатуры калькулятора
def get_calculator_keyboard():
    keyboard = [
        [InlineKeyboardButton("1", callback_data="calc_1"), InlineKeyboardButton("2", callback_data="calc_2"), InlineKeyboardButton("3", callback_data="calc_3")],
        [InlineKeyboardButton("4", callback_data="calc_4"), InlineKeyboardButton("5", callback_data="calc_5"), InlineKeyboardButton("6", callback_data="calc_6")],
        [InlineKeyboardButton("7", callback_data="calc_7"), InlineKeyboardButton("8", callback_data="calc_8"), InlineKeyboardButton("9", callback_data="calc_9")],
        [InlineKeyboardButton("0", callback_data="calc_0"), InlineKeyboardButton("⬅️", callback_data="calc_backspace"), InlineKeyboardButton("C", callback_data="calc_clear")],
        [InlineKeyboardButton("✅ Рассчитать", callback_data="calc_confirm")]
    ]
    return InlineKeyboardMarkup(keyboard)


# Обработчик нажатий на кнопки калькулятора
async def handle_calculator(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    user_id = query.from_user.id
    data = query.data

    if user_id not in user_calculator:
        user_calculator[user_id] = {"input": "", "base_currency": None}

    if data.startswith("calc_"):
        action = data.replace("calc_", "")
        if action.isdigit():
            user_calculator[user_id]["input"] += action
        elif action == "backspace":
            user_calculator[user_id]["input"] = user_calculator[user_id]["input"][:-1]
        elif action == "clear":
            user_calculator[user_id]["input"] = ""

    await query.answer()
    await query.edit_message_text(
        text=f"Введите сумму: {user_calculator[user_id]['input']}",
        reply_markup=get_calculator_keyboard()
    )

# Обработчик подтверждения расчета
async def confirm_calculation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    user_id = query.from_user.id

    if user_calculator[user_id]["input"] == "":
        await query.answer("Сначала введите сумму!", show_alert=True)
        return

    context.user_data['state'] = 'awaiting_currency'
    await query.edit_message_text(
        text=f"Вы ввели сумму: {user_calculator[user_id]['input']}\nВыберите валюту для конвертации:",
        reply_markup=get_currency_keyboard(prefix="calc_")
    )

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
		base_rate = rates[base_currency]  # Курс базовой валюты к рублю

		# Формируем таблицу
		message = "<pre>"
		message += "{:<10} {:<15}\n".format("Валюта", f"Курс {SUPPORTED_CURRENCIES[base_currency]['name']} ({base_currency})")
		message += "-" * 26 + "\n"

		for currency, rate in rates.items():
			if currency != base_currency:
				# Пересчёт курсов
				if base_currency == "RUB":
					converted_rate = 1 / rate  # Если базовая валюта рубль
				else:
					converted_rate = rate / base_rate  # Пересчёт относительно базовой валюты
				message += "{:<10} {:<15}\n".format(currency, format_number(converted_rate))

		message += "</pre>"
	else:
		message = "Не удалось получить курсы валют. Попробуйте позже."



	# Отображаем курс
	await query.edit_message_text(text=message, parse_mode="HTML")

	#тестовое сообщение с курсами валют
	message = f"Курсы валют\n"
	message += "<pre>"  # Используем форматирование HTML для красивого вывода
	message += "{:<10} {:<15}\n".format("Валюта", "Курс")
	message += "-" * 26 + "\n"
	for currency, rate in rates.items():
		message += "{:<10} {:<15}\n".format(currency, 1/rate)
	message += "</pre>"
	# Отправка сообщения в Telegram
	await context.bot.send_message(
		chat_id=query.message.chat_id,
		text=message,
		parse_mode="HTML"
	)


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

# Обработка заявки (по этапам)
async def handle_request_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
	query = update.callback_query
	user_id = query.from_user.id
	text = query.data
	state = context.user_data.get('state')

	# Проверяем, есть ли активное состояние
	if not state:
		await query.answer("Неизвестное состояние. Попробуйте снова.", show_alert=True)
		await start(update, context)  # Возвращаемся в главное меню
		return

	# Этап выбора валюты, которую отдать
	if state == 'awaiting_from_currency':
		if text.startswith("req_"):
			from_currency = text.split("_")[1]
			user_requests[user_id]['from_currency'] = from_currency
			context.user_data['state'] = 'awaiting_amount'
			await query.edit_message_text(
			   f"Вы выбрали: {SUPPORTED_CURRENCIES[from_currency]['name']} ({from_currency}). Введите сумму для обмена:"
			)
		else:
			await query.answer("Ошибка выбора валюты. Попробуйте ещё раз.", show_alert=True)

	# Этап ввода суммы
	elif state == 'awaiting_amount':
		try:
			amount = float(text)
			if amount <= 0:
				raise ValueError("Сумма должна быть больше нуля.")
			user_requests[user_id]['amount'] = amount
			context.user_data['state'] = 'awaiting_to_currency'
			from_currency = user_requests[user_id]['from_currency']
			await query.message.reply_text(
				"Выберите валюту, на которую хотите обменять:",
				reply_markup=get_currency_keyboard(prefix="req_", exclude=from_currency)
			)
		except ValueError:
			await query.answer("Введите корректную сумму!", show_alert=True)

	# Этап выбора валюты, которую хотят получить
	elif state == 'awaiting_to_currency':
		if text.startswith("req_"):
			to_currency = text.split("_")[1]
			user_requests[user_id]['to_currency'] = to_currency
			from_currency = user_requests[user_id]['from_currency']
			amount = user_requests[user_id]['amount']
			rates = get_exchange_rate(from_currency)

			if rates:
				exchange_rate = rates.get(to_currency)
				if exchange_rate:
					# Расчет суммы с учетом базовой валюты
					if from_currency == "RUB":
						converted_amount = amount * exchange_rate  # RUB → другая валюта
					elif to_currency == "RUB":
						converted_amount = amount / exchange_rate  # Другая валюта → RUB
					else:
						converted_amount = amount / exchange_rate  # Стандартный расчет

					user_requests[user_id]['converted_amount'] = converted_amount
					context.user_data['state'] = 'awaiting_confirmation'
					await query.edit_message_text(
						f"Вы хотите обменять {amount} {from_currency} на {converted_amount:.2f} {to_currency}. Подтвердить?",
						reply_markup=InlineKeyboardMarkup([
							[InlineKeyboardButton("Да", callback_data="confirm_yes")],
							[InlineKeyboardButton("Нет", callback_data="confirm_no")]
						])
					)
				else:
					await query.edit_message_text("Не удалось получить курс для выбранной валюты.")
			else:
				await query.edit_message_text("Не удалось получить курсы валют. Попробуйте позже.")
		else:
			await query.answer("Ошибка выбора валюты. Попробуйте ещё раз.", show_alert=True)

# Обработка текста для этапа ввода суммы
async def handle_text_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
	user_id = update.effective_user.id
	text = update.message.text
	state = context.user_data.get('state')

	if state == 'awaiting_amount':
		try:
			amount = float(text)
			if amount <= 0:
				raise ValueError("Сумма должна быть больше нуля.")
			user_requests[user_id]['amount'] = amount
			context.user_data['state'] = 'awaiting_to_currency'
			from_currency = user_requests[user_id]['from_currency']
			await update.message.reply_text(
				"Выберите валюту, на которую хотите обменять:",
				reply_markup=get_currency_keyboard(prefix="req_", exclude=from_currency)
			)
		except ValueError:
			await update.message.reply_text("Введите корректную сумму (больше нуля):")

# Обработка подтверждения
async def handle_request_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
	query = update.callback_query
	if query.data == "confirm_yes":
		user_request = user_requests.get(query.from_user.id, {})
		amount = user_request.get('amount')
		converted_amount = user_request.get('converted_amount')
		from_currency = user_request.get('from_currency')
		to_currency = user_request.get('to_currency')

		await query.answer("Вы выбрали: Да.")
		await query.edit_message_text(
			f"Заявка успешно сохранена!\n"
			f"Обмен: {amount:.2f} {from_currency} на {converted_amount:.2f} {to_currency}."
		)
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
	application.add_handler(CallbackQueryHandler(handle_request_input, pattern="^req_.*$"))
	application.add_handler(CallbackQueryHandler(handle_request_confirmation, pattern="^confirm_.*$"))
	application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_input))

	application.run_polling()

if __name__ == "__main__":
	main()