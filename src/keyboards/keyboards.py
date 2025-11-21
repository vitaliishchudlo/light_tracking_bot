from aiogram.types import InlineKeyboardButton
from aiogram.types import KeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.utils.keyboard import ReplyKeyboardBuilder

from src.constants import QUEUES
from src.services.db import subscriptions_collection
from typing import List


def get_subscribe_keyboard():
    builder = ReplyKeyboardBuilder()

    builder.row(KeyboardButton(text="📊 Мої графіки 📅"))
    builder.row(KeyboardButton(text="⚙ Налаштування черг ⚡"))

    keyboard = builder.as_markup(resize_keyboard=True, one_time_keyboard=False)

    return keyboard


def get_group_keyboard(user_id: int):
    builder = InlineKeyboardBuilder()

    user_subscriptions = list(subscriptions_collection.find({"id_telegram": user_id}))
    # Support both old 'group_number' and new 'queue' field names
    subscribed_queues = [sub.get('queue') or sub.get('group_number') for sub in user_subscriptions if sub.get('queue') or sub.get('group_number')]

    for queue in QUEUES:
        text = f"✅ {queue}" if queue in subscribed_queues else queue

        button = InlineKeyboardButton(text=text,
                                      callback_data=f"queue_unsubscribe_{queue}" if queue in subscribed_queues else f"queue_subscribe_{queue}")
        builder.add(button)

    # Adjust the rows: 2 columns for each row
    builder.adjust(2, 2, 2, 2, 2, 2)

    return builder.as_markup()
