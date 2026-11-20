import logging
from datetime import datetime

from aiogram import Router, Bot
from aiogram.types import CallbackQuery
from src.constants import QUEUES
from src.handlers.get_graphs import send_graphs
from src.constants import REMINDER_OFFSETS, REMINDER_KINDS, format_offset
from src.handlers.notification_settings import NOTIFICATIONS_MENU_TEXT, QUIET_HOURS_TEXT, REMINDERS_TEXT
from src.keyboards.keyboards import (
    get_group_keyboard,
    get_notification_settings_keyboard,
    get_notifications_menu_keyboard,
    get_reminders_keyboard,
)
from src.services.db import get_subscriptions_collection, get_user_settings_collection

logger = logging.getLogger(__name__)

router: Router = Router()


async def handle_queue_subscription(callback_query: CallbackQuery, bot: Bot, queue: str):
    chat_id = callback_query.message.chat.id
    message_id = callback_query.message.message_id
    user = callback_query.from_user

    if queue in QUEUES:
        try:
            subscriptions_collection = get_subscriptions_collection()
            # Check if already subscribed (support both old and new field names)
            existing = (subscriptions_collection.find_one({"id_telegram": user.id, "queue": queue}) or
                        subscriptions_collection.find_one({"id_telegram": user.id, "group_number": queue}))
            
            if not existing:
                # Insert user data into the MongoDB collection
                subscriptions_collection.insert_one({
                    "id_telegram": user.id,
                    "firstname": user.first_name,
                    "second_name": user.last_name,
                    "username": user.username,
                    "queue": queue,
                    "date_subscribed": datetime.now()
                })
        except Exception as e:
            logger.error(f"Error subscribing to queue {queue}: {e}")
            await bot.answer_callback_query(callback_query.id, text="Помилка підключення до бази даних. Спробуйте пізніше.")
            return

        await bot.edit_message_reply_markup(
            chat_id=chat_id,
            message_id=message_id,
            reply_markup=get_group_keyboard(user.id)
        )
        await bot.answer_callback_query(callback_query.id, text=f"Підписано на чергу {queue}")



async def handle_queue_unsubscription(callback_query: CallbackQuery, bot: Bot, queue: str):
    chat_id = callback_query.message.chat.id
    message_id = callback_query.message.message_id
    user = callback_query.from_user

    if queue in QUEUES:
        try:
            subscriptions_collection = get_subscriptions_collection()
            # Remove user data from the MongoDB collection (support both old and new field names)
            # Delete by queue field
            subscriptions_collection.delete_one({"id_telegram": user.id, "queue": queue})
            # Delete by group_number field (old format)
            subscriptions_collection.delete_one({"id_telegram": user.id, "group_number": queue})
        except Exception as e:
            logger.error(f"Error unsubscribing from queue {queue}: {e}")
            await bot.answer_callback_query(callback_query.id, text="Помилка підключення до бази даних. Спробуйте пізніше.")
            return

        await bot.edit_message_reply_markup(
            chat_id=chat_id,
            message_id=message_id,
            reply_markup=get_group_keyboard(user.id)
        )
        await bot.answer_callback_query(callback_query.id, text=f"Успішно відписано від черги {queue}")


async def handle_notification_settings(callback_query: CallbackQuery, bot: Bot, mode: str):
    """Handle notification mode selection"""
    chat_id = callback_query.message.chat.id
    message_id = callback_query.message.message_id
    user = callback_query.from_user
    
    # Valid modes
    valid_modes = ['always', '22-06', '22-08', '00-06', '00-08', '00-10', 'disabled']
    
    if mode not in valid_modes:
        await bot.answer_callback_query(callback_query.id, text="Невірний режим")
        return
    
    try:
        user_settings_collection = get_user_settings_collection()
        # Get current mode
        user_settings = user_settings_collection.find_one({"id_telegram": user.id})
        current_mode = user_settings.get('notification_mode', 'always') if user_settings else 'always'
        
        # If same mode selected, don't update
        if mode == current_mode:
            await bot.answer_callback_query(callback_query.id, text="Цей режим вже вибрано")
            return
        
        # Update or create user settings
        user_settings_collection.update_one(
            {"id_telegram": user.id},
            {
                "$set": {
                    "id_telegram": user.id,
                    "notification_mode": mode,
                    "updated_at": datetime.now()
                }
            },
            upsert=True
        )
    except Exception as e:
        logger.error(f"Error updating notification settings: {e}")
        await bot.answer_callback_query(callback_query.id, text="Помилка підключення до бази даних. Спробуйте пізніше.")
        return
    
    # Update keyboard
    await bot.edit_message_reply_markup(
        chat_id=chat_id,
        message_id=message_id,
        reply_markup=get_notification_settings_keyboard(user.id)
    )
    
    # Show confirmation
    mode_names = {
        'always': 'Завжди',
        '22-06': '22:00 - 06:00',
        '22-08': '22:00 - 08:00',
        '00-06': '00:00 - 06:00',
        '00-08': '00:00 - 08:00',
        '00-10': '00:00 - 10:00',
        'disabled': 'Вимкнуто'
    }
    await bot.answer_callback_query(
        callback_query.id, 
        text=f"Режим змінено на: {mode_names.get(mode, mode)}"
    )


async def show_screen(callback_query: CallbackQuery, text: str, reply_markup):
    """Switch the settings message to another screen (edit in place)"""
    await callback_query.message.edit_text(text=text, reply_markup=reply_markup)
    await callback_query.answer()


async def handle_reminder_toggle(callback_query: CallbackQuery, kind: str, minutes: int):
    """Turn one reminder (before power off / on, N minutes) on or off"""
    user = callback_query.from_user
    field = f"reminders_{kind}"
    try:
        settings_collection = get_user_settings_collection()
        current = (settings_collection.find_one({"id_telegram": user.id}) or {}).get(field, [])
        enabled = minutes not in current
        settings_collection.update_one(
            {"id_telegram": user.id},
            {
                ("$addToSet" if enabled else "$pull"): {field: minutes},
                "$set": {"updated_at": datetime.now()},
            },
            upsert=True,
        )
    except Exception as e:
        logger.error(f"Error updating reminders for user {user.id}: {e}")
        await callback_query.answer("Помилка підключення до бази даних. Спробуйте пізніше.")
        return

    await callback_query.message.edit_reply_markup(reply_markup=get_reminders_keyboard(user.id))
    what = "вимкненням" if kind == "off" else "увімкненням"
    state = "увімкнено" if enabled else "вимкнено"
    await callback_query.answer(f"Нагадування за {format_offset(minutes)} перед {what} {state}")


@router.callback_query()
async def handle_callback_query(callback_query: CallbackQuery, bot: Bot):
    data = callback_query.data

    if data.startswith("queue_"):
        if "_subscribe_" in data:
            queue = data.split("_subscribe_")[-1]
            return await handle_queue_subscription(callback_query, bot, queue)
        if "_unsubscribe_" in data:
            queue = data.split("_unsubscribe_")[-1]
            return await handle_queue_unsubscription(callback_query, bot, queue)

    # Backward compatibility with old group_ callbacks
    if data.startswith("group_"):
        if "_subscribe_" in data:
            queue = data.split("_subscribe_")[-1]
            return await handle_queue_subscription(callback_query, bot, queue)
        if "_unsubscribe_" in data:
            queue = data.split("_unsubscribe_")[-1]
            return await handle_queue_unsubscription(callback_query, bot, queue)
    
    # Handle notification mode selection
    if data.startswith("notification_mode_"):
        mode = data.split("notification_mode_")[-1]
        return await handle_notification_settings(callback_query, bot, mode)
    
    # Notifications section screens
    if data == "notif_menu":
        return await show_screen(callback_query, NOTIFICATIONS_MENU_TEXT, get_notifications_menu_keyboard())
    if data == "notif_quiet":
        return await show_screen(callback_query, QUIET_HOURS_TEXT,
                                 get_notification_settings_keyboard(callback_query.from_user.id))
    if data == "notif_reminders":
        return await show_screen(callback_query, REMINDERS_TEXT,
                                 get_reminders_keyboard(callback_query.from_user.id))

    # Reminder toggles: rem_off_15, rem_on_60, ...
    if data.startswith("rem_"):
        _, kind, minutes = data.split("_")
        if kind in REMINDER_KINDS and minutes.isdigit() and int(minutes) in REMINDER_OFFSETS:
            return await handle_reminder_toggle(callback_query, kind, int(minutes))

    # Column headers in the reminders keyboard
    if data == "noop":
        return await callback_query.answer()

    # Show user's schedules (inline button under the queue list)
    if data == "show_graphs":
        await bot.answer_callback_query(callback_query.id)
        return await send_graphs(bot, chat_id=callback_query.message.chat.id, user_id=callback_query.from_user.id)

    # Unknown callback
    await bot.answer_callback_query(callback_query.id, text="Невідома команда")
