from datetime import datetime

from aiogram import Router, Bot
from aiogram.types import CallbackQuery
from aiogram.types import InputMediaPhoto, FSInputFile
from src.handlers.get_graphs import get_graphs
from src.constants import GROUPS_NUMBERS
from src.keyboards.keyboards import get_group_keyboard
from src.services.db import subscriptions_collection

router: Router = Router()


async def handle_group_subscription(callback_query: CallbackQuery, bot: Bot, group: str):
    chat_id = callback_query.message.chat.id
    message_id = callback_query.message.message_id
    user = callback_query.from_user

    if group in GROUPS_NUMBERS:
        # Insert user data into the MongoDB collection
        subscriptions_collection.insert_one({
            "id_telegram": user.id,
            "firstname": user.first_name,
            "second_name": user.last_name,
            "username": user.username,
            "group_number": group,
            "date_subscribed": datetime.now()
        })

        await bot.edit_message_reply_markup(
            chat_id=chat_id,
            message_id=message_id,
            reply_markup=get_group_keyboard(user.id)
        )
        await bot.answer_callback_query(callback_query.id, text=f"Підписано на групу №{group}")



async def handle_group_unsubscription(callback_query: CallbackQuery, bot: Bot, group: str):
    chat_id = callback_query.message.chat.id
    message_id = callback_query.message.message_id
    user = callback_query.from_user

    if group in GROUPS_NUMBERS:
        # Remove user data from the MongoDB collection
        subscriptions_collection.delete_one({
            "id_telegram": user.id,
            "group_number": group
        })

        await bot.edit_message_reply_markup(
            chat_id=chat_id,
            message_id=message_id,
            reply_markup=get_group_keyboard(user.id)
        )
        await bot.answer_callback_query(callback_query.id, text=f"Успішно відписано від групи №{group}")


async def handle_get_graphs_for_user(callback_query: CallbackQuery, bot: Bot):
    return await get_graphs(message=callback_query.message, bot=bot, callback_query=callback_query)



@router.callback_query()
async def handle_callback_query(callback_query: CallbackQuery, bot: Bot):
    data = callback_query.data

    if data.startswith("group_"):
        if "_subscribe_" in data:
            return await handle_group_subscription(callback_query, bot, data.split("_")[-1])
        if "_unsubscribe_" in data:
            return await handle_group_unsubscription(callback_query, bot, data.split("_")[-1])

    if data == "get_my_graphs":
        return await handle_get_graphs_for_user(callback_query, bot)

    # Add here other handling
    else:
        await bot.answer_callback_query(callback_query.id, text="Невідома команда")
