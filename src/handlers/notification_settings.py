from aiogram import Router, Bot, F
from aiogram.types import Message

from src.constants import BTN_NOTIFICATIONS, OLD_BTN_NOTIFICATIONS
from src.keyboards.keyboards import get_notifications_menu_keyboard

router: Router = Router()


NOTIFICATIONS_MENU_TEXT = (
    "🔔 <b>Сповіщення</b>\n\n"
    "🌙 <b>Тихі години</b> — коли сповіщення приходять без звуку, або вимкнути їх зовсім\n\n"
    "⏰ <b>Нагадування</b> — попередження за кілька хвилин до вимкнення чи увімкнення світла"
)

QUIET_HOURS_TEXT = (
    "🌙 <b>Тихі години</b>\n\n"
    "Оберіть режим отримання сповіщень:\n\n"
    "• <b>Завжди</b> - отримувати всі сповіщення зі звуком\n"
    "• <b>Нічний режим</b> - отримувати сповіщення без звуку в зазначений період, зі звуком в інший час\n"
    "• <b>Вимкнути</b> - не отримувати жодних сповіщень (і нагадувань теж)"
)

REMINDERS_TEXT = (
    "⏰ <b>Нагадування</b>\n\n"
    "Встанови одне чи кілька нагадувань, щоб не пропустити вимкнення світла "
    "або знати, коли його увімкнуть.\n\n"
    "Коли тобі нагадувати?"
)


@router.message(F.text.in_({BTN_NOTIFICATIONS, OLD_BTN_NOTIFICATIONS}))
async def show_notification_settings(message: Message, bot: Bot):
    await bot.send_message(
        chat_id=message.chat.id,
        text=NOTIFICATIONS_MENU_TEXT,
        reply_markup=get_notifications_menu_keyboard(),
    )
