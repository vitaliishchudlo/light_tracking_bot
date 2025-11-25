from aiogram import Router, Bot, F
from aiogram.types import Message

from src.keyboards.keyboards import get_notification_settings_keyboard

router: Router = Router()


@router.message(F.text == '⚙ Налаштування сповіщень 🔔')
async def show_notification_settings(message: Message, bot: Bot):
    explanation_text = (
        "🔔 <b>Налаштування сповіщень</b>\n\n"
        "Оберіть режим отримання сповіщень:\n\n"
        "• <b>Завжди</b> - отримувати всі сповіщення зі звуком\n"
        "• <b>Нічний режим</b> - отримувати сповіщення без звуку в зазначений період, зі звуком в інший час\n"
        "• <b>Вимкнути</b> - не отримувати сповіщення взагалі"
    )
    
    await bot.send_message(
        chat_id=message.chat.id,
        text=explanation_text,
        parse_mode='HTML',
        reply_markup=get_notification_settings_keyboard(message.from_user.id)
    )

