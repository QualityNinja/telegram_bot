import logging
import asyncio
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
        [KeyboardButton("Старт"), KeyboardButton("Удалить уведомление")],
        [KeyboardButton("Показать сохраненные уведомления")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

# Команда /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_chat.id
    user_data[user_id] = {"step": "text", "notifications": []}
    await update.message.reply_text("Привет! Введите текст уведомления:", reply_markup=get_keyboard())

# Обработчик текстовых сообщений
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_chat.id
    message = update.message.text

    if message == "Старт":
        await start(update, context)
        return
    elif message == "Удалить уведомление":
        await delete_notification_prompt(update, context)
        return
    elif message == "Показать сохраненные уведомления":
        await show_saved_notifications(update, context)
        return
    elif message == "Назад":
        await update.message.reply_text("Вы вернулись на предыдущее состояние.", reply_markup=get_keyboard())
        return
    elif message.startswith("Удалить уведомление "):
        await delete_notification_by_number(update, context, int(message.split()[-1]) - 1)
        return

    # ... (остальной код функции handle_message остается без изменений)

# Обработчик для удаления уведомления по номеру
async def delete_notification_by_number(update: Update, context: ContextTypes.DEFAULT_TYPE, notification_number):
    user_id = update.effective_chat.id
    if 0 <= notification_number < len(user_data[user_id]["notifications"]):
        scheduler.remove_job(f"notification_{user_id}_{notification_number + 1}")
        del user_data[user_id]["notifications"][notification_number]

        # Обновление job_ids и перенумерация
        for i in range(notification_number, len(user_data[user_id]["notifications"])):
            old_job_id = f"notification_{user_id}_{i + 2}"
            new_job_id = f"notification_{user_id}_{i + 1}"
            scheduler.reschedule_job(old_job_id, id=new_job_id)

        await update.message.reply_text("Уведомление удалено.", reply_markup=get_keyboard())
    else:
        await update.message.reply_text("Неверный номер уведомления.", reply_markup=get_keyboard())

# Обработчик для показа сохраненных уведомлений
async def show_saved_notifications(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_chat.id
    if user_id in user_data and user_data[user_id]["notifications"]:
        notifications = user_data[user_id]["notifications"]
        message_text = "Сохраненные уведомления:\n"
        keyboard = [[KeyboardButton("Назад")]]
        for i, notification in enumerate(notifications, start=1):
            message_text += f"\nНомер: {i}\nТекст: {notification['text']}\nДата и время: {notification['date'].strftime('%Y-%m-%d %H:%M (UTC)')}\n"
            keyboard.append([KeyboardButton(f"Удалить уведомление {i}")])
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        await update.message.reply_text(message_text, reply_markup=reply_markup)
    else:
        await update.message.reply_text("У вас нет сохраненных уведомлений.", reply_markup=get_keyboard())

# Запуск бота
if __name__ == "__main__":
    application = ApplicationBuilder().token("7899393512:AAFb8-b4_fa9EBKHNaxTPmYlUof4nnMo4h4").build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    logging.info("Бот запущен!")
    application.run_polling()

