from datetime import datetime

from aiogram import Router, Bot
from aiogram.types import CallbackQuery
from src.constants import QUEUES
from src.keyboards.keyboards import get_group_keyboard
from src.services.db import subscriptions_collection

router: Router = Router()


async def handle_queue_subscription(callback_query: CallbackQuery, bot: Bot, queue: str):
    chat_id = callback_query.message.chat.id
    message_id = callback_query.message.message_id
    user = callback_query.from_user

    if queue in QUEUES:
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
        # Remove user data from the MongoDB collection (support both old and new field names)
        # Delete by queue field
        subscriptions_collection.delete_one({"id_telegram": user.id, "queue": queue})
        # Delete by group_number field (old format)
        subscriptions_collection.delete_one({"id_telegram": user.id, "group_number": queue})

        await bot.edit_message_reply_markup(
            chat_id=chat_id,
            message_id=message_id,
            reply_markup=get_group_keyboard(user.id)
        )
        await bot.answer_callback_query(callback_query.id, text=f"Успішно відписано від черги {queue}")


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
    
    # Unknown callback
    await bot.answer_callback_query(callback_query.id, text="Невідома команда")
