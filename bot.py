#!/usr/bin/env python
# pylint: disable=unused-argument
# This work is dedicated to the public domain under the Creative Commons CC0 License.

"""
Простой бот для ответа на сообщения Telegram.

Сначала определяются несколько функций-обработчиков. Затем эти функции передаются
приложению и регистрируются в соответствующих местах.
Затем бот запускается и работает до тех пор, пока мы не нажмем Ctrl-C в командной строке.

"""

import logging
import os

from dotenv import load_dotenv
from telegram import ForceReply, Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
# установите более высокий уровень регистрации для httpx, чтобы не регистрировать все GET- и POST-запросы
logging.getLogger("httpx").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)


# Определите несколько обработчиков команд. Обычно они принимают два аргумента update и контекст
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a message when the command /start is issued."""
    user = update.effective_user
    await update.message.reply_html(
        rf"Hi {user.mention_html()}!",
        reply_markup=ForceReply(selective=True),
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a message when the command /help is issued."""
    await update.message.reply_text("Help!")


async def echo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Echo the user message."""
    await update.message.reply_text(update.message.text)


def main() -> None:
    """Start the bot."""
    load_dotenv()

    # Создайте приложение и передайте ему токен вашего бота.
    application = Application.builder().token(os.environ["TOKEN"]).build()

    # на разные команды - ответ в Telegram
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))

    # при отсутствии команды, т.е. сообщения - отправьте эхо сообщения в Telegram
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo))

    # Запускайте бота до тех пор, пока пользователь не нажмет Ctrl-C
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
