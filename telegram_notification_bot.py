import logging
import asyncio
import uuid
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
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

# Функция для создания клавиатуры
def get_keyboard():
    keyboard = [
        [KeyboardButton("Старт"), KeyboardButton("Удалить последнее уведомление")],
        [KeyboardButton("Показать сохраненные уведомления")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

# Команда /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_chat.id
    user_data[user_id] = {"step": "text", "notifications": {}}
    await update.message.reply_text("Привет! Введите текст уведомления:", reply_markup=get_keyboard())

# Обработчик текстовых сообщений
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_chat.id
    message = update.message.text

    if message == "Старт":
        await start(update, context)
        return
    elif message == "Удалить последнее уведомление":
        await delete_last_notification(update, context)
        return
    elif message == "Показать сохраненные уведомления":
        await show_saved_notifications(update, context)
        return

    if user_id not in user_data or "step" not in user_data[user_id]:
        await update.message.reply_text("Пожалуйста, начните с команды /start.", reply_markup=get_keyboard())
        return

    if user_data[user_id]["step"] == "text":
        user_data[user_id]["current_text"] = message
        user_data[user_id]["step"] = "date"
        await update.message.reply_text(
            "Введите дату и время для уведомления в формате YYYY-MM-DD HH:MM (например, 2025-01-05 14:30):",
            reply_markup=get_keyboard()
        )
    elif user_data[user_id]["step"] == "date":
        try:
            notification_time = datetime.strptime(message, "%Y-%m-%d %H:%M")
            notification_time = timezone("Europe/Moscow").localize(notification_time)

            notification_id = str(uuid.uuid4())
            user_data[user_id]["notifications"][notification_id] = {
                "text": user_data[user_id]["current_text"],
                "date": notification_time
            }
            user_data[user_id]["step"] = None  # Завершаем ввод

            job_name = f"notification_{notification_id}"
            scheduler.add_job(
                send_notification_wrapper,
                'date',
                run_date=notification_time,
                args=[user_id, notification_id],
                id=job_name
            )

            await update.message.reply_text(
                f"Уведомление сохранено! Мы отправим его {notification_time.strftime('%Y-%m-%d %H:%M')} (UTC).",
                reply_markup=get_keyboard()
            )
        except ValueError:
            await update.message.reply_text("Неверный формат даты. Попробуйте снова.", reply_markup=get_keyboard())

# Обработчик для удаления последнего уведомления
async def delete_last_notification(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_chat.id
    if user_id in user_data and user_data[user_id]["notifications"]:
        last_notification_id = list(user_data[user_id]["notifications"].keys())[-1]
        del user_data[user_id]["notifications"][last_notification_id]
        scheduler.remove_job(f"notification_{last_notification_id}")
        await update.message.reply_text("Последнее уведомление удалено.", reply_markup=get_keyboard())
    else:
        await update.message.reply_text("У вас нет сохраненных уведомлений.", reply_markup=get_keyboard())

# Обработчик для показа сохраненных уведомлений
async def show_saved_notifications(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_chat.id
    if user_id in user_data and user_data[user_id]["notifications"]:
        notifications = user_data[user_id]["notifications"]
        message_text = "Сохраненные уведомления:\n"
        for notification_id, notification in notifications.items():
            message_text += f"\nID: {notification_id}\nТекст: {notification['text']}\nДата и время: {notification['date'].strftime('%Y-%m-%d %H:%M (UTC)')}\n"
        await update.message.reply_text(message_text, reply_markup=get_keyboard())
    else:
        await update.message.reply_text("У вас нет сохраненных уведомлений.", reply_markup=get_keyboard())

# Отправка уведомления
def send_notification_wrapper(user_id, notification_id):
    new_loop = asyncio.new_event_loop()
    asyncio.set_event_loop(new_loop)
    new_loop.run_until_complete(send_notification(user_id, notification_id))

async def send_notification(user_id, notification_id):
    try:
        if user_id in user_data and notification_id in user_data[user_id]["notifications"]:
            text = user_data[user_id]["notifications"][notification_id]["text"]
            await application.bot.send_message(chat_id=user_id, text=f"Напоминание: {text}")
            del user_data[user_id]["notifications"][notification_id]
            logging.info(f"Уведомление отправлено пользователю {user_id}: {text}")
        else:
            logging.warning(f"Уведомление для пользователя {user_id} не найдено.")
    except Exception as e:
        logging.error(f"Ошибка при отправке уведомления пользователю {user_id}: {e}")

# Запуск бота
if __name__ == "__main__":
    application = ApplicationBuilder().token("7899393512:AAFb8-b4_fa9EBKHNaxTPmYlUof4nnMo4h4").build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    logging.info("Бот запущен!")
    application.run_polling()
