import logging

from aiogram import Router, Bot, F
from aiogram.types import Message
from datetime import datetime, timedelta
from typing import Optional

from src.constants import format_offset, BTN_GRAPHS, BTN_QUEUES, OLD_BTN_GRAPHS, OLD_BTN_QUEUES
from src.keyboards.keyboards import get_subscribe_keyboard, get_group_keyboard
from src.services.db import get_subscriptions_collection, get_schedules_collection

logger = logging.getLogger(__name__)

router: Router = Router()


@router.message(F.text.in_({BTN_QUEUES, OLD_BTN_QUEUES}))
async def show_queue_settings(message: Message, bot: Bot):
    await bot.send_message(
        chat_id=message.chat.id,
        text="Оберіть черги для підписки або відписки:",
        reply_markup=get_group_keyboard(message.from_user.id)
    )


@router.message(F.text.in_({BTN_GRAPHS, OLD_BTN_GRAPHS}))
async def get_graphs(message: Message, bot: Bot):
    await send_graphs(bot, chat_id=message.chat.id, user_id=message.from_user.id, reply_to=message)


async def send_graphs(bot: Bot, chat_id: int, user_id: int, reply_to: Optional[Message] = None):
    """Send schedules for all user's queues. Used by the menu button and the inline button."""

    async def _answer(text: str, **kwargs):
        # First message is a reply when triggered by a user message, otherwise a plain message
        if reply_to is not None:
            return await reply_to.reply(text=text, **kwargs)
        return await bot.send_message(chat_id=chat_id, text=text, **kwargs)

    # Get a list of queues the user is subscribed to
    try:
        subscriptions_collection = get_subscriptions_collection()
        subscriptions = list(subscriptions_collection.find({"id_telegram": user_id}))
        queues = {sub.get("queue") or sub.get("group_number") for sub in subscriptions}  # Support both old and new field names
    except Exception as e:
        logger.error(f"Error getting subscriptions: {e}")
        return await _answer(
            text="Помилка підключення до бази даних. Спробуйте пізніше.",
            reply_markup=get_subscribe_keyboard()
        )

    if not queues:
        return await _answer(
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

    def _is_shutdown_started(event_date: str, shutdown_from: str) -> bool:
        """Check if shutdown has already started (start time <= now)"""
        date_obj = _parse_date(event_date)
        from_time = _parse_time(shutdown_from)
        if not date_obj or not from_time:
            return False
        return datetime.combine(date_obj.date(), from_time) <= datetime.now()

    # Fetch schedules from database (not API to avoid rate limiting)
    schedules_collection = get_schedules_collection()
    all_messages = []
    
    if schedules_collection is None:
        logger.warning("schedules_collection not initialized, cannot fetch schedules from DB")
        return await _answer(
            text="Наразі сервіс недоступний. Спробуйте пізніше.",
            reply_markup=get_subscribe_keyboard()
        )
    
    for queue in sorted(queues):
        try:
            # Get stored schedule from database
            doc = await schedules_collection.find_one({"queue": queue})
            
            # Format message for this queue
            message_parts = [f"<b>Графік для черги <u>{queue}</u>💡</b>"]
            
            # Check if schedule exists
            schedule = {}
            initially_empty_dates = set()
            if doc:
                if doc.get('schedule'):
                    schedule = doc.get('schedule', {})
                    if not isinstance(schedule, dict):
                        schedule = {}
                # Get dates that were initially empty (not cancellations)
                initially_empty_dates = set(doc.get('initially_empty_dates', []))
            
            # Sort by event date
            sorted_dates = sorted(schedule.keys()) if schedule else []
            today = datetime.now().date()
            
            # Collect all dates (including cancelled ones) for today and future
            valid_dates = []
            for event_date in sorted_dates:
                date_obj = _parse_date(event_date)
                if date_obj and date_obj.date() < today:
                    continue
                # Include date even if shutdowns is empty (cancelled)
                valid_dates.append(event_date)
            
            def _calculate_duration(from_time_str: str, to_time_str: str) -> str:
                """Calculate duration between two times and return formatted string like 'на 2 год 30хв'"""
                try:
                    from_time = _parse_time(from_time_str)
                    to_time = _parse_time(to_time_str)
                    
                    if not from_time or not to_time:
                        return ""
                    
                    # Create datetime objects for calculation
                    from_dt = datetime.combine(datetime.now().date(), from_time)
                    to_dt = datetime.combine(datetime.now().date(), to_time)
                    
                    # Handle case where to_time is 00:00 (means next day)
                    if to_time_str == "00:00":
                        to_dt += timedelta(days=1)
                    
                    # Calculate difference
                    duration = to_dt - from_dt
                    total_minutes = int(duration.total_seconds() / 60)
                    
                    
                    # Format duration string: '3 год', '3 год 30 хв', '30 хв'
                    return f"на {format_offset(total_minutes)}"
                except Exception as e:
                    logger.error(f"Error calculating duration: {e}")
                    return ""
            
            if valid_dates:
                # There are dates (active or cancelled) for this queue
                for event_date in valid_dates:
                    date_data = schedule.get(event_date, {})
                    shutdowns = date_data.get('shutdowns', [])
                    
                    message_parts.append(f"\n📅 <b><i>{event_date}</i></b>")
                    
                    if not shutdowns:
                        # No shutdowns - check if it's initially empty or cancelled
                        if event_date in initially_empty_dates:
                            # This date appeared with empty shutdowns (not a cancellation)
                            message_parts.append(f"<blockquote>🟢 Для цієї групи світло не вимикатимуть</blockquote>")
                        else:
                            # Schedule was cancelled (had shutdowns, now empty)
                            message_parts.append(f"<blockquote>🟢 Графік скасовано ⚡️</blockquote>")
                    else:
                        # Each shutdown in separate blockquote
                        for shutdown in shutdowns:
                            hours = shutdown.get('shutdownHours', '')
                            from_time = shutdown.get('from', '')
                            to_time = shutdown.get('to', '')
                            
                            if hours and from_time and to_time:
                                # Format hours with spaces: "10:30 - 13:30"
                                hours_formatted = hours.replace('-', ' - ')
                                
                                # Calculate duration
                                duration = _calculate_duration(from_time, to_time)
                                duration_text = f" – (<i>{duration}</i>)" if duration else ""
                                
                                # Check if shutdown is in the past
                                is_past = _is_shutdown_past(event_date, from_time, to_time)
                                
                                if is_past:
                                    # Past shutdown: white circle and strikethrough everything
                                    shutdown_line = f"⚪️ {hours_formatted}{duration_text}"
                                    message_parts.append(f"<blockquote><s>{shutdown_line}</s></blockquote>")
                                else:
                                    # Active shutdown: red circle, arrow if it is happening right now
                                    arrow = "→ " if _is_shutdown_started(event_date, from_time) else ""
                                    shutdown_line = f"🔴 {arrow}{hours_formatted}{duration_text}"
                                    message_parts.append(f"<blockquote>{shutdown_line}</blockquote>")
            else:
                # No schedule data or all dates are in the past - show that there's no schedule
                today_str = datetime.now().strftime('%d.%m.%Y')
                message_parts.append(f"\n📅 {today_str}")
                message_parts.append(f"<blockquote>🟢 Графік відсутній</blockquote>")
            
            # Always add message for this queue (even if no schedule)
            all_messages.append("\n".join(message_parts))
        
        except Exception as e:
            logger.error(f"Error fetching schedule from DB for queue {queue}: {e}", exc_info=True)
            continue
    
    # all_messages will always contain at least one message per queue now
    # (we removed the check that skipped queues without schedules)
    
    # Send messages
    for i, msg_text in enumerate(all_messages):
        # Send first message as reply, others as new messages
        if i == 0:
            await _answer(msg_text, parse_mode='HTML', reply_markup=get_subscribe_keyboard())
        else:
            await bot.send_message(
                chat_id=chat_id,
                text=msg_text,
                parse_mode='HTML',
                reply_markup=get_subscribe_keyboard()
            )
