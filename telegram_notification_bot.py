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

            notification = {
                "text": user_data[user_id]["current_text"],
                "date": notification_time
            }
            user_data[user_id]["notifications"].append(notification)
            user_data[user_id]["step"] = None  # Завершаем ввод

            job_name = f"notification_{user_id}_{len(user_data[user_id]['notifications'])}"
            scheduler.add_job(
                send_notification_wrapper,
                'date',
                run_date=notification_time,
                args=[user_id, len(user_data[user_id]['notifications']) - 1],
                id=job_name
            )

            await update.message.reply_text(
                f"Уведомление сохранено! Мы отправим его {notification_time.strftime('%Y-%m-%d %H:%M')} (UTC).",
                reply_markup=get_keyboard()
            )
        except ValueError:
            await update.message.reply_text("Неверный формат даты. Попробуйте снова.", reply_markup=get_keyboard())

# Обработчик для удаления уведомления по номеру
async def delete_notification_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_chat.id
    if user_id in user_data and user_data[user_id]["notifications"]:
        await update.message.reply_text("Введите номер уведомления, которое хотите удалить:")
        user_data[user_id]["step"] = "delete"
    else:
        await update.message.reply_text("У вас нет сохраненных уведомлений.", reply_markup=get_keyboard())

async def delete_notification(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_chat.id
    if user_data[user_id]["step"] == "delete":
        try:
            notification_number = int(update.message.text) - 1
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
                await update.message.reply_text("Неверный номер уведомления. Попробуйте снова.", reply_markup=get_keyboard())
        except ValueError:
            await update.message.reply_text("Введите корректный номер.", reply_markup=get_keyboard())

# Обработчик для показа сохраненных уведомлений
async def show_saved_notifications(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_chat.id
    if user_id in user_data and user_data[user_id]["notifications"]:
        notifications = user_data[user_id]["notifications"]
        message_text = "Сохраненные уведомления:\n"
        for i, notification in enumerate(notifications, start=1):
            message_text += f"\nНомер: {i}\nТекст: {notification['text']}\nДата и время: {notification['date'].strftime('%Y-%m-%d %H:%M (UTC)')}\n"
        await update.message.reply_text(message_text, reply_markup=get_keyboard())
    else:
        await update.message.reply_text("У вас нет сохраненных уведомлений.", reply_markup=get_keyboard())

# Отправка уведомления
def send_notification_wrapper(user_id, notification_number):
    new_loop = asyncio.new_event_loop()
    asyncio.set_event_loop(new_loop)
    new_loop.run_until_complete(send_notification(user_id, notification_number))

async def send_notification(user_id, notification_number):
    try:
        if user_id in user_data and notification_number < len(user_data[user_id]["notifications"]):
            notification = user_data[user_id]["notifications"][notification_number]
            await application.bot.send_message(chat_id=user_id, text=f"Напоминание: {notification['text']}")
            del user_data[user_id]["notifications"][notification_number]
            logging.info(f"Уведомление отправлено пользователю {user_id}: {notification['text']}")
        else:
            logging.warning(f"Уведомление для пользователя {user_id} не найдено.")
    except Exception as e:
        logging.error(f"Ошибка при отправке уведомления пользователю {user_id}: {e}")

# Запуск бота
if __name__ == "__main__":
    application = ApplicationBuilder().token("7899393512:AAFb8-b4_fa9EBKHNaxTPmYlUof4nnMo4h4").build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, delete_notification))
    logging.info("Бот запущен!")
    application.run_polling()
