import logging

from aiogram import Router, Bot, F
from aiogram.types import Message
from datetime import datetime, timedelta

from src.keyboards.keyboards import get_subscribe_keyboard, get_group_keyboard
from src.services.db import subscriptions_collection, get_schedules_collection

logger = logging.getLogger(__name__)

router: Router = Router()


@router.message(F.text == '⚙ Налаштування черг ⚡')
async def show_queue_settings(message: Message, bot: Bot):
    await bot.send_message(
        chat_id=message.chat.id,
        text="Оберіть черги для підписки або відписки:",
        reply_markup=get_group_keyboard(message.from_user.id)
    )


@router.message(F.text == '📊 Мої графіки 📅')
async def get_graphs(message: Message, bot: Bot):
    user_id = message.from_user.id

    # Get a list of queues the user is subscribed to
    subscriptions = list(subscriptions_collection.find({"id_telegram": user_id}))
    queues = {sub.get("queue") or sub.get("group_number") for sub in subscriptions}  # Support both old and new field names

    if not queues:
        return await message.reply(
            text="Спочатку Вам потрібно підписатись на чергу",
            reply_markup=get_subscribe_keyboard()
        )

    def _parse_date(date_str: str):
        """Parse date string in format DD.MM.YYYY"""
        try:
            return datetime.strptime(date_str, "%d.%m.%Y")
        except ValueError:
            return None
    
    def _parse_time(time_str: str):
        """Parse time string in format HH:MM"""
        try:
            return datetime.strptime(time_str, "%H:%M").time()
        except ValueError:
            return None
    
    def _is_shutdown_past(event_date: str, shutdown_from: str, shutdown_to: str) -> bool:
        """Check if shutdown is in the past"""
        try:
            date_obj = _parse_date(event_date)
            if not date_obj:
                return False
            
            from_time = _parse_time(shutdown_from)
            to_time = _parse_time(shutdown_to)
            
            if not from_time or not to_time:
                return False
            
            # Create datetime for shutdown end time
            shutdown_end = datetime.combine(date_obj.date(), to_time)
            
            # Handle case where to_time is 00:00 (means it ends at midnight, next day)
            if shutdown_to == "00:00":
                shutdown_end += timedelta(days=1)
            
            now = datetime.now()
            return shutdown_end < now
        except Exception as e:
            logger.error(f"Error checking if shutdown is past: {e}")
            return False
    
    # Fetch schedules from database (not API to avoid rate limiting)
    schedules_collection = get_schedules_collection()
    all_messages = []
    
    if schedules_collection is None:
        logger.warning("schedules_collection not initialized, cannot fetch schedules from DB")
        return await message.reply(
            text="Наразі сервіс недоступний. Спробуйте пізніше.",
            reply_markup=get_subscribe_keyboard()
        )
    
    for queue in sorted(queues):
        try:
            # Get stored schedule from database
            doc = await schedules_collection.find_one({"queue": queue})
            
            if not doc or not doc.get('schedule'):
                logger.debug(f"No schedule data in DB for queue {queue}")
                continue
            
            schedule = doc.get('schedule', {})
            if not schedule or not isinstance(schedule, dict):
                continue
            
            # Format message for this queue
            message_parts = [f"💡 <b>Графік для черги <u>{queue}</u></b>"]
            
            # Sort by event date
            sorted_dates = sorted(schedule.keys())
            
            for event_date in sorted_dates:
                date_data = schedule.get(event_date, {})
                shutdowns = date_data.get('shutdowns', [])
                
                if not shutdowns:
                    continue
                
                message_parts.append(f"\n\n📅 {event_date}\n")
                
                for shutdown in shutdowns:
                    hours = shutdown.get('shutdownHours', '')
                    from_time = shutdown.get('from', '')
                    to_time = shutdown.get('to', '')
                    
                    if hours:
                        # Check if shutdown is in the past
                        is_past = _is_shutdown_past(event_date, from_time, to_time)
                        if is_past:
                            message_parts.append(f"   <s>🔴️ {hours}</s>")
                        else:
                            message_parts.append(f"   🔴️ {hours}")
                
                approved_since = date_data.get('scheduleApprovedSince')
                if approved_since:
                    message_parts.append(f"\n📌 Оновлено: {approved_since}")
            
            if len(message_parts) > 1:  # More than just the header
                all_messages.append("\n".join(message_parts))
        
        except Exception as e:
            logger.error(f"Error fetching schedule from DB for queue {queue}: {e}", exc_info=True)
            continue
    
    if not all_messages:
        return await message.reply(
            text="Наразі немає даних про графіки відключень",
            reply_markup=get_subscribe_keyboard()
        )
    
    # Send messages
    for i, msg_text in enumerate(all_messages):
        # Send first message as reply, others as new messages
        if i == 0:
            await message.reply(text=msg_text, parse_mode='HTML', reply_markup=get_subscribe_keyboard())
        else:
            await bot.send_message(
                chat_id=message.chat.id,
                text=msg_text,
                parse_mode='HTML',
                reply_markup=get_subscribe_keyboard()
            )
