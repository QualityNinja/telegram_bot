import logging
import asyncio
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime
from pytz import timezone

# Логирование
logging.basicConfig(format="%(asctime)s - %(message)s", level=logging.INFO)

# Инициализация планировщика
scheduler = BackgroundScheduler(timezone=timezone("UTC"))
scheduler.start()

# Хранилище уведомлений
user_data = {}

# Команда /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_chat.id
    user_data[user_id] = {"step": "text"}
    await update.message.reply_text("Привет! Введите текст уведомления:")

# Обработчик текстовых сообщений
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_chat.id
    message = update.message.text

    if user_id not in user_data or "step" not in user_data[user_id]:
        await update.message.reply_text("Пожалуйста, начните с команды /start.")
        return

    if user_data[user_id]["step"] == "text":
        # Сохраняем текст уведомления
        user_data[user_id]["text"] = message
        user_data[user_id]["step"] = "date"
        await update.message.reply_text(
            "Введите дату и время для уведомления в формате YYYY-MM-DD HH:MM (например, 2025-01-05 14:30):"
        )
    elif user_data[user_id]["step"] == "date":
        try:
            # Сохраняем дату уведомления
            notification_time = datetime.strptime(message, "%Y-%m-%d %H:%M")
            notification_time = timezone("Europe/Moscow").localize(notification_time)

            user_data[user_id]["date"] = notification_time
            user_data[user_id]["step"] = None  # Завершаем ввод

            # Планируем уведомление
            job_name = f"notification_{user_id}_{notification_time}"
            # Добавляем задачу
            scheduler.add_job(
                send_notification_wrapper,  # Вызов обертки для асинхронной функции
                'date',
                run_date=notification_time,
                args=[user_id],  # Аргумент для задачи
                id=job_name
            )

            await update.message.reply_text(
                f"Уведомление сохранено! Мы отправим его {notification_time.strftime('%Y-%m-%d %H:%M')} (UTC)."
            )
        except ValueError:
            await update.message.reply_text("Неверный формат даты. Попробуйте снова.")


# Отправка уведомления
def send_notification_wrapper(user_id):
    # Создание нового цикла событий для работы в отдельном потоке
    new_loop = asyncio.new_event_loop()
    asyncio.set_event_loop(new_loop)
    new_loop.run_until_complete(send_notification(user_id))

async def send_notification(user_id):
    try:
        if user_id in user_data and "text" in user_data[user_id]:
            text = user_data[user_id]["text"]
            await application.bot.send_message(chat_id=user_id, text=f"Напоминание: {text}")
            del user_data[user_id]  # Удаляем данные после отправки уведомления
            logging.info(f"Уведомление отправлено пользователю {user_id}: {text}")
        else:
            logging.warning(f"Уведомление для пользователя {user_id} не найдено.")
    except Exception as e:
        logging.error(f"Ошибка при отправке уведомления пользователю {user_id}: {e}")


# Запуск бота
if __name__ == "__main__":
    application = ApplicationBuilder().token("7899393512:AAFb8-b4_fa9EBKHNaxTPmYlUof4nnMo4h4").build()

    # Обработчики команд и сообщений
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logging.info("Бот запущен!")
    application.run_polling()
