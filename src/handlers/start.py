from aiogram import Router, Bot
from aiogram.filters import Command
from aiogram.types import Message

from src.keyboards.keyboards import get_subscribe_keyboard

router: Router = Router()


@router.message(Command("start"))
async def handle_start_command(message: Message, bot: Bot):
    greeting_text = (
        f"Привіт, {message.from_user.first_name if message.from_user.first_name else message.from_user.username}!\n"
        "Гайда відстежувати появу світла разом 💡"
    )
    await bot.send_message(chat_id=message.chat.id, text=greeting_text, reply_markup=get_subscribe_keyboard())
