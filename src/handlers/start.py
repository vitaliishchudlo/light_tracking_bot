from aiogram import Router, Bot
from aiogram.filters import Command
from aiogram.types import Message

from src.keyboards.keyboards import get_subscribe_keyboard, get_group_keyboard
router: Router = Router()


@router.message(Command("start"))
async def handle_start_command(message: Message, bot: Bot):
    
    
    greeting_text = (
        f"Привіт, {message.from_user.first_name if message.from_user.first_name else message.from_user.username}!\n\n"
        "🤖 Бот для відстеження вимкнення світла в Івано-Франківську\n\n"
        "Підпишись на черги, які тебе цікавлять, і отримуй сповіщення про зміни в графіку відключень 💡"
    )
    await bot.send_message(
        chat_id=message.chat.id, 
        text=greeting_text, 
        reply_markup=get_subscribe_keyboard()
    )
    
    # Show queue selection keyboard
    await bot.send_message(
        chat_id=message.chat.id,
        text="Обери черги для відстежування:",
        reply_markup=get_group_keyboard(message.from_user.id)
    )
