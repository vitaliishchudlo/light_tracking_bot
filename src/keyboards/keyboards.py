from aiogram.types import InlineKeyboardButton
from aiogram.types import KeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.utils.keyboard import ReplyKeyboardBuilder

from src.constants import GROUPS_NUMBERS
from src.services.db import subscriptions_collection


def get_subscribe_keyboard():
    builder = ReplyKeyboardBuilder()

    builder.row(KeyboardButton(text="📊 Мої графіки 📅"))
    builder.row(KeyboardButton(text="⚙ Налаштування черг ⚡"))

    keyboard = builder.as_markup(resize_keyboard=True, one_time_keyboard=False)

    return keyboard


def get_group_keyboard(user_id: int):
    builder = InlineKeyboardBuilder()

    user_subscriptions = subscriptions_collection.find({"id_telegram": user_id})
    subscribed_groups = [sub['group_number'] for sub in user_subscriptions]

    for number in GROUPS_NUMBERS:
        text = f"✅ {number}" if number in subscribed_groups else number

        button = InlineKeyboardButton(text=text,
                                      callback_data=f"group_unsubscribe_{number}" if number in subscribed_groups else f"group_subscribe_{number}")
        builder.add(button)

    builder.add(InlineKeyboardButton(text="Отримати графіки для моїх груп", callback_data=f"get_my_graphs"))

    # Adjust the rows (optional, based on your desired layout)
    builder.adjust(2, 2, 2, 2, 2, 5, 1)

    return builder.as_markup()
