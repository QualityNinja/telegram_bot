import logging
import asyncio
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime
from pytz import timezone
import uuid

# Логирование
logging.basicConfig(format="%(asctime)s - %(message)s", level=logging.INFO)

# Инициализация планировщика
scheduler = BackgroundScheduler(timezone=timezone("UTC"))
scheduler.start()

# Хранилище уведомлений
user_data = {}

# Функция для создания клавиатуры
def get_keyboard(user_id, notifications_page=False):
    keyboard = []

    if notifications_page:
        if user_id in user_data and user_data[user_id]["notifications"]:
            for i, notification in enumerate(user_data[user_id]["notifications"], start=1):
                keyboard.append([KeyboardButton(f"Удалить уведомление № {i}")])
        keyboard.append([KeyboardButton("Назад")])
    else:
        keyboard.append([KeyboardButton("Старт"), KeyboardButton("Удалить уведомление")])
        keyboard.append([KeyboardButton("Показать сохраненные уведомления")])

    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


# Команда /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_chat.id
    user_data[user_id] = {"step": "text", "notifications": [], "previous_step": None}
    await update.message.reply_text("Привет! Введите текст уведомления:", reply_markup=get_keyboard(user_id))


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
        await go_back(update, context)
        return

    # Обработка шагов (текст -> дата)
    if user_id not in user_data or "step" not in user_data[user_id]:
        await update.message.reply_text("Пожалуйста, начните с команды /start.", reply_markup=get_keyboard(user_id))
        return

    if user_data[user_id]["step"] == "text":
        user_data[user_id]["current_text"] = message
        user_data[user_id]["step"] = "date"
        user_data[user_id]["previous_step"] = "text"
        await update.message.reply_text(
            "Введите дату и время для уведомления в формате YYYY-MM-DD HH:MM (например, 2025-01-05 14:30):",
            reply_markup=get_keyboard(user_id)
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

            # Генерация уникального job_id с использованием uuid
            job_name = str(uuid.uuid4())  # Генерация уникального ID

            scheduler.add_job(
                send_notification_wrapper,
                'date',
                run_date=notification_time,
                args=[user_id, len(user_data[user_id]['notifications']) - 1],
                id=job_name
            )

            await update.message.reply_text(
                f"Уведомление '{user_data[user_id]['current_text']}' успешно сохранено для {notification_time.strftime('%Y-%m-%d %H:%M')}.",
                reply_markup=get_keyboard(user_id)
            )
        except ValueError:
            await update.message.reply_text("Неверный формат даты. Попробуйте снова.", reply_markup=get_keyboard(user_id))


# Функция для перехода назад
async def go_back(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_chat.id
    if user_id in user_data and user_data[user_id]["previous_step"]:
        previous_step = user_data[user_id]["previous_step"]
        user_data[user_id]["step"] = previous_step
        user_data[user_id]["previous_step"] = None

        if previous_step == "text":
            await update.message.reply_text("Введите текст уведомления:", reply_markup=get_keyboard(user_id))
        elif previous_step == "date":
            await update.message.reply_text("Введите текст уведомления:", reply_markup=get_keyboard(user_id))
    else:
        await update.message.reply_text("Вы находитесь на главном экране.", reply_markup=get_keyboard(user_id))


# Обработчик для удаления уведомлений
async def delete_notification_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_chat.id
    if user_id in user_data and user_data[user_id]["notifications"]:
        await update.message.reply_text("Выберите уведомление для удаления:", reply_markup=get_keyboard(user_id, notifications_page=True))
    else:
        await update.message.reply_text("У вас нет сохраненных уведомлений.", reply_markup=get_keyboard(user_id))


# Обработчик для удаления уведомлений
async def delete_notification(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_chat.id
    message = update.message.text

    if message.startswith("Удалить уведомление №"):
        try:
            notification_number = int(message.split()[-1]) - 1
            if 0 <= notification_number < len(user_data[user_id]["notifications"]):
                # Удаляем уведомление из списка
                del user_data[user_id]["notifications"][notification_number]

                # Обновляем задачи в планировщике
                job_name = f"notification_{user_id}_{notification_number}"
                scheduler.remove_job(job_name)

                # Обновляем клавиатуру и информируем пользователя
                await update.message.reply_text("Уведомление удалено.",
                                                reply_markup=get_keyboard(user_id, notifications_page=True))
            else:
                await update.message.reply_text("Неверный номер уведомления. Попробуйте снова.",
                                                reply_markup=get_keyboard(user_id, notifications_page=True))
        except ValueError:
            await update.message.reply_text("Введите корректный номер.",
                                            reply_markup=get_keyboard(user_id, notifications_page=True))


# Показываем все сохраненные уведомления
async def show_saved_notifications(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_chat.id
    if user_id in user_data and user_data[user_id]["notifications"]:
        notifications = user_data[user_id]["notifications"]
        message_text = "Сохраненные уведомления:\n"
        for i, notification in enumerate(notifications, start=1):
            message_text += f"\nНомер: {i}\nТекст: {notification['text']}\nДата и время: {notification['date'].strftime('%Y-%m-%d %H:%M (UTC)')}\n"
        await update.message.reply_text(message_text, reply_markup=get_keyboard(user_id, notifications_page=True))
    else:
        await update.message.reply_text("У вас нет сохраненных уведомлений.", reply_markup=get_keyboard(user_id))


# Отправка уведомления
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


# Обертка для отправки уведомлений (упрощение асинхронной работы)
def send_notification_wrapper(user_id, notification_number):
    asyncio.create_task(send_notification(user_id, notification_number))


# Запуск бота
if __name__ == "__main__":
    application = ApplicationBuilder().token("7899393512:AAFb8-b4_fa9EBKHNaxTPmYlUof4nnMo4h4").build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    logging.info("Бот запущен!")
    application.run_polling()
