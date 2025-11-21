import logging

from aiogram import Router, Bot, F
from aiogram.types import Message

from src.keyboards.keyboards import get_subscribe_keyboard, get_group_keyboard
from src.services.db import subscriptions_collection
from src.services.api_client import ScheduleAPI

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

    # Fetch current schedules from API
    api_client = ScheduleAPI()
    all_messages = []
    
    for queue in sorted(queues):
        try:
            schedule_data = await api_client.fetch_schedule(queue)
            
            if not schedule_data:
                continue
            
            # Format message for this queue
            message_parts = [f"💡 <b>Графік для черги № {queue}</b>"]
            
            # Sort by event date
            sorted_items = sorted(schedule_data, key=lambda x: x.get('eventDate', ''))
            
            for item in sorted_items:
                event_date = item.get('eventDate')
                if not event_date:
                    continue
                
                queues_data = item.get('queues', {}).get(queue, [])
                if not queues_data:
                    continue
                
                message_parts.append(f"\n\n📅 {event_date}\n")
                
                for shutdown in queues_data:
                    hours = shutdown.get('shutdownHours', '')
                    if hours:
                        message_parts.append(f"   🔴️ {hours}")
                
                approved_since = item.get('scheduleApprovedSince')
                if approved_since:
                    message_parts.append(f"\n📌 Оновлено: {approved_since}")
            
            if len(message_parts) > 1:  # More than just the header
                all_messages.append("\n".join(message_parts))
        
        except Exception as e:
            logger.error(f"Error fetching schedule for queue {queue}: {e}")
            continue
    
    await api_client.close()
    
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
