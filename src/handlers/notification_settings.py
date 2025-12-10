from aiogram import Router, Bot, F
from aiogram.types import Message

from src.keyboards.keyboards import get_notification_settings_keyboard

router: Router = Router()


@router.message(F.text == 'Налаштування сповіщень🔔')
async def show_notification_settings(message: Message, bot: Bot):
    explanation_text = (
        "🔔 Налаштування сповіщень\n\n"
        "Оберіть режим отримання сповіщень:\n\n"
        "• Завжди - отримувати всі сповіщення зі звуком\n"
        "• Нічний режим - отримувати сповіщення без звуку в зазначений період, зі звуком в інший час\n"
        "• Вимкнути - не отримувати жодних сповіщень"
    )
    
    await bot.send_message(
        chat_id=message.chat.id,
        text=explanation_text,
        reply_markup=get_notification_settings_keyboard(message.from_user.id)
    )

