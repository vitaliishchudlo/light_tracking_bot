from aiogram.types import InlineKeyboardButton
from aiogram.types import KeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.utils.keyboard import ReplyKeyboardBuilder

from src.constants import QUEUES, BTN_GRAPHS, BTN_QUEUES, BTN_NOTIFICATIONS, REMINDER_OFFSETS, format_offset
from src.services.db import get_subscriptions_collection, get_user_settings_collection
from typing import List


def get_subscribe_keyboard():
    builder = ReplyKeyboardBuilder()

    builder.row(KeyboardButton(text=BTN_GRAPHS))
    builder.row(KeyboardButton(text=BTN_QUEUES), KeyboardButton(text=BTN_NOTIFICATIONS))

    keyboard = builder.as_markup(resize_keyboard=True, one_time_keyboard=False)

    return keyboard


def get_group_keyboard(user_id: int):
    builder = InlineKeyboardBuilder()

    try:
        subscriptions_collection = get_subscriptions_collection()
        user_subscriptions = list(subscriptions_collection.find({"id_telegram": user_id}))
        # Support both old 'group_number' and new 'queue' field names
        subscribed_queues = [sub.get('queue') or sub.get('group_number') for sub in user_subscriptions if sub.get('queue') or sub.get('group_number')]
    except Exception:
        subscribed_queues = []

    for queue in QUEUES:
        text = f"✅ {queue}" if queue in subscribed_queues else queue

        button = InlineKeyboardButton(text=text,
                                      callback_data=f"queue_unsubscribe_{queue}" if queue in subscribed_queues else f"queue_subscribe_{queue}")
        builder.add(button)

    # Way out of the queue list: show schedules (also brings back the main menu keyboard)
    builder.add(InlineKeyboardButton(text="📊 Показати мої графіки", callback_data="show_graphs"))

    # Adjust the rows: 2 columns for each queue row, last row - "show schedules" button
    builder.adjust(2, 2, 2, 2, 2, 2, 1)

    return builder.as_markup()


def get_notification_settings_keyboard(user_id: int):
    """Create inline keyboard for notification settings"""
    builder = InlineKeyboardBuilder()
    
    # Get current user settings
    try:
        user_settings_collection = get_user_settings_collection()
        user_settings = user_settings_collection.find_one({"id_telegram": user_id})
        current_mode = user_settings.get('notification_mode', 'always') if user_settings else 'always'
    except Exception:
        current_mode = 'always'
    
    # Define notification modes (emojis at the end)
    modes = [
        ('always', 'Завжди'),
        ('22-06', '22:00 - 06:00 🌙'),
        ('22-08', '22:00 - 08:00 🌙'),
        ('00-06', '00:00 - 06:00 🌙'),
        ('00-08', '00:00 - 08:00 🌙'),
        ('00-10', '00:00 - 10:00 🌙'),
        ('disabled', 'Вимкнути 🚫')
    ]
    
    # Add buttons with checkmark for current mode
    for mode, label in modes:
        if mode == current_mode:
            text = f"✅ {label}"
        else:
            text = label
        builder.add(InlineKeyboardButton(
            text=text,
            callback_data=f"notification_mode_{mode}"
        ))
    
    # Layout according to user requirements:
    # Row 1: "Завжди" (1 button)
    # Row 2: "22:00-06:00" та "22:00-08:00" (2 buttons)
    # Row 3: "00:00-06:00", "00:00-08:00" (2 buttons)
    # Row 4: "00:00-10:00" (1 button)
    # Row 5: "Вимкнути" (1 button)
    builder.add(InlineKeyboardButton(text="⬅️ Назад", callback_data="notif_menu"))
    builder.adjust(1, 2, 2, 1, 1, 1)

    return builder.as_markup()


def get_notifications_menu_keyboard():
    """Notifications section: quiet hours or reminders"""
    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(text="🌙 Тихі години", callback_data="notif_quiet"))
    builder.add(InlineKeyboardButton(text="⏰ Нагадування", callback_data="notif_reminders"))
    builder.adjust(2)
    return builder.as_markup()


def get_user_reminders(user_id: int) -> dict:
    """Returns {"off": {minutes...}, "on": {minutes...}} - selected reminders of the user"""
    try:
        settings = get_user_settings_collection().find_one({"id_telegram": user_id}) or {}
    except Exception:
        settings = {}
    return {
        "off": set(settings.get("reminders_off", [])),
        "on": set(settings.get("reminders_on", [])),
    }


def get_reminders_keyboard(user_id: int):
    """Two independent columns: before power off (left) and before power on (right)"""
    selected = get_user_reminders(user_id)
    builder = InlineKeyboardBuilder()

    # Column headers (not clickable)
    builder.add(InlineKeyboardButton(text="🔴 Перед вимкненням", callback_data="noop"))
    builder.add(InlineKeyboardButton(text="🟢 Перед увімкненням", callback_data="noop"))

    for minutes in REMINDER_OFFSETS:
        for kind in ("off", "on"):
            mark = "✅ " if minutes in selected[kind] else ""
            builder.add(InlineKeyboardButton(
                text=f"{mark}за {format_offset(minutes)}",
                callback_data=f"rem_{kind}_{minutes}",
            ))

    builder.add(InlineKeyboardButton(text="⬅️ Назад", callback_data="notif_menu"))
    builder.adjust(*([2] * (len(REMINDER_OFFSETS) + 1)), 1)
    return builder.as_markup()
