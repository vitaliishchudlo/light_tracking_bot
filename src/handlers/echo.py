from aiogram import Router, Bot
from aiogram.enums import ParseMode
from aiogram.types import Message

from src.keyboards.keyboards import get_group_keyboard

router: Router = Router()


@router.message()
async def process_any_message(message: Message, bot: Bot):
    await bot.send_message(
        chat_id=message.chat.id,
        text="Список актуальних черг, на які можна *підписатися* чи *відписатися*:",
        parse_mode=ParseMode.MARKDOWN_V2,
        reply_markup=get_group_keyboard(message.chat.id),
    )
