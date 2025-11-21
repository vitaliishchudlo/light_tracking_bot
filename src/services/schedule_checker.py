import asyncio
import logging
from typing import Dict, List, Any, Optional
from datetime import datetime
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from src.services.api_client import ScheduleAPI
from src.services.db import get_schedules_collection, subscriptions_collection
from src.constants import QUEUES
from aiogram import Bot

logger = logging.getLogger(__name__)


class ScheduleChecker:
    """Service for checking schedule updates and notifying subscribers"""
    
    def __init__(self, bot: Bot):
        self.bot = bot
        self.api_client = ScheduleAPI()
        self.scheduler = AsyncIOScheduler()
        self.is_running = False
    
    async def start(self):
        """Start the scheduler"""
        if self.is_running:
            return
        
        self.is_running = True
        # Run every minute
        self.scheduler.add_job(
            self.check_all_queues,
            trigger=IntervalTrigger(minutes=1),
            id='check_schedules',
            replace_existing=True
        )
        self.scheduler.start()
        logger.info("Schedule checker started")
    
    async def stop(self):
        """Stop the scheduler"""
        if self.scheduler.running:
            self.scheduler.shutdown()
        await self.api_client.close()
        self.is_running = False
        logger.info("Schedule checker stopped")
    
    def _normalize_schedule(self, schedule_data: List[Dict[str, Any]], queue: str) -> Dict[str, Any]:
        """
        Normalize schedule data for comparison
        
        Args:
            schedule_data: Raw schedule data from API
            queue: Queue number
            
        Returns:
            Normalized schedule dict with eventDate and shutdowns
        """
        normalized = {}
        
        for item in schedule_data:
            event_date = item.get('eventDate')
            if not event_date:
                continue
            
            queues_data = item.get('queues', {}).get(queue, [])
            if not queues_data:
                continue
            
            shutdowns = []
            for shutdown in queues_data:
                shutdowns.append({
                    'from': shutdown.get('from'),
                    'to': shutdown.get('to'),
                    'shutdownHours': shutdown.get('shutdownHours'),
                    'status': shutdown.get('status')
                })
            
            normalized[event_date] = {
                'shutdowns': shutdowns,
                'createdAt': item.get('createdAt'),
                'scheduleApprovedSince': item.get('scheduleApprovedSince')
            }
        
        return normalized
    
    def _has_changes(self, old_schedule: Dict[str, Any], new_schedule: Dict[str, Any]) -> bool:
        """
        Check if schedule has changed
        
        Args:
            old_schedule: Previous schedule state
            new_schedule: New schedule state
            
        Returns:
            True if there are changes in actual schedule data (not just metadata)
        """
        # First time - save schedule but don't notify (return False to skip notification)
        # This prevents spamming users on first run
        if not old_schedule or len(old_schedule) == 0:
            logger.info(f"First time checking this queue or empty old schedule - saving schedule without notification. Old: {old_schedule}, New dates: {list(new_schedule.keys())}")
            return False
        
        # Compare by event dates and shutdowns
        old_dates = set(old_schedule.keys())
        new_dates = set(new_schedule.keys())
        
        # Check if dates changed
        if old_dates != new_dates:
            logger.info(f"Schedule dates changed: old={old_dates}, new={new_dates}")
            return True
        
        # Check if shutdowns changed for each date
        for date in new_dates:
            old_date_data = old_schedule.get(date, {})
            new_date_data = new_schedule.get(date, {})
            
            old_shutdowns = old_date_data.get('shutdowns', [])
            new_shutdowns = new_date_data.get('shutdowns', [])
            
            # Compare shutdowns count
            if len(old_shutdowns) != len(new_shutdowns):
                logger.info(f"Shutdown count changed for {date}: old={len(old_shutdowns)}, new={len(new_shutdowns)}")
                return True
            
            # Compare each shutdown by creating a set of (from, to) tuples
            old_shutdown_set = {(sh.get('from'), sh.get('to')) for sh in old_shutdowns}
            new_shutdown_set = {(sh.get('from'), sh.get('to')) for sh in new_shutdowns}
            
            if old_shutdown_set != new_shutdown_set:
                logger.info(f"Shutdown times changed for {date}: old={old_shutdown_set}, new={new_shutdown_set}")
                return True
        
        # Don't notify on scheduleApprovedSince changes alone - only on actual schedule changes
        logger.debug("No changes detected in schedule data")
        return False
    
    async def _get_stored_schedule(self, queue: str) -> Optional[Dict[str, Any]]:
        """Get stored schedule from database"""
        schedules_collection = get_schedules_collection()
        if schedules_collection is None:
            logger.warning("schedules_collection is not initialized - cannot retrieve stored schedule")
            return None
            
        try:
            doc = await schedules_collection.find_one({"queue": queue})
            if doc:
                schedule = doc.get('schedule', {})
                if schedule and isinstance(schedule, dict):
                    logger.info(f"Retrieved stored schedule for {queue}: {len(schedule)} dates - {list(schedule.keys())[:3]}")
                    return schedule
                else:
                    logger.warning(f"Stored schedule for {queue} is empty or invalid: {schedule}")
                    return None
            logger.info(f"No stored schedule found for {queue} in database")
            return None
        except Exception as e:
            logger.error(f"Error retrieving stored schedule for {queue}: {e}", exc_info=True)
            return None
    
    async def _save_schedule(self, queue: str, schedule: Dict[str, Any], approved_since: Optional[str] = None):
        """Save schedule to database"""
        schedules_collection = get_schedules_collection()
        if schedules_collection is None:
            logger.error("schedules_collection is not initialized - cannot save schedule")
            return
        
        try:
            result = await schedules_collection.update_one(
                {"queue": queue},
                {
                    "$set": {
                        "schedule": schedule,
                        "lastChecked": datetime.now(),
                        "scheduleApprovedSince": approved_since
                    }
                },
                upsert=True
            )
            if result.upserted_id:
                logger.info(f"Created new schedule record for {queue} with {len(schedule)} dates")
            elif result.modified_count > 0:
                logger.info(f"Updated schedule for {queue} with {len(schedule)} dates")
            else:
                logger.debug(f"Schedule for {queue} unchanged")
        except Exception as e:
            logger.error(f"Error saving schedule for {queue}: {e}", exc_info=True)
    
    def _format_notification_message(self, queue: str, schedule: Dict[str, Any]) -> str:
        """
        Format notification message for users
        
        Args:
            queue: Queue number
            schedule: Schedule data
            
        Returns:
            Formatted message
        """
        message_parts = [f"🔔❗️ <b>Зміни у графіку для черги <u>{queue}</u></b>"]

        # Sort dates
        sorted_dates = sorted(schedule.keys())
        
        for date in sorted_dates:
            date_data = schedule[date]
            shutdowns = date_data.get('shutdowns', [])
            
            if shutdowns:
                message_parts.append(f"\n\n📅 {date}\n")
                for shutdown in shutdowns:
                    hours = shutdown.get('shutdownHours', '')
                    if hours:
                        message_parts.append(f"   🔴️ {hours}")
                
                approved_since = date_data.get('scheduleApprovedSince')
                if approved_since:
                    message_parts.append(f"\n  📌 Оновлено: {approved_since}")
        
        return "\n".join(message_parts)
    
    async def _notify_subscribers(self, queue: str, message: str):
        """Notify all subscribers of a queue about changes"""
        # Get all subscribers for this queue
        # Run sync MongoDB query in thread pool to avoid blocking
        loop = asyncio.get_event_loop()
        subscribers = await loop.run_in_executor(
            None,
            lambda: list(subscriptions_collection.find({
                "$or": [
                    {"queue": queue},
                    {"group_number": queue}  # Support old field name
                ]
            }))
        )
        
        notified_count = 0
        failed_count = 0
        
        for subscriber in subscribers:
            try:
                user_id = subscriber.get('id_telegram')
                if user_id:
                    await self.bot.send_message(
                        chat_id=user_id,
                        text=message,
                        parse_mode='HTML'
                    )
                    notified_count += 1
                    # Small delay to avoid rate limiting
                    await asyncio.sleep(0.05)
            except Exception as e:
                failed_count += 1
                user_id = subscriber.get('id_telegram', 'unknown')
                logger.error(f"Failed to notify user {user_id} about queue {queue}: {e}")
        
        logger.info(f"Notified {notified_count} subscribers about queue {queue} (failed: {failed_count})")
    
    async def check_queue(self, queue: str) -> bool:
        """
        Check a single queue for updates
        
        Args:
            queue: Queue number to check
            
        Returns:
            True if changes were detected and notifications sent
        """
        try:
            # Fetch current schedule from API
            schedule_data = await self.api_client.fetch_schedule(queue)
            
            if not schedule_data:
                logger.warning(f"No data received for queue {queue}")
                return False
            
            # Normalize the schedule
            new_schedule = self._normalize_schedule(schedule_data, queue)
            logger.debug(f"Fetched schedule for {queue}: {len(new_schedule)} dates")
            
            # Get stored schedule
            old_schedule = await self._get_stored_schedule(queue)
            if old_schedule:
                logger.debug(f"Retrieved old schedule for {queue}: {len(old_schedule)} dates")
            else:
                logger.debug(f"No old schedule found for {queue}")
            
            # Get the latest approved since timestamp from the new schedule
            latest_approved = None
            for date, date_data in new_schedule.items():
                approved = date_data.get('scheduleApprovedSince')
                if approved:
                    if not latest_approved or approved > latest_approved:
                        latest_approved = approved
            
            # Check for changes
            has_changes = self._has_changes(old_schedule, new_schedule)
            
            # Always save the latest schedule to database
            await self._save_schedule(queue, new_schedule, latest_approved)
            
            # Only notify if there are actual changes
            if has_changes:
                logger.info(f"Changes detected for queue {queue} - notifying subscribers")
                
                # Notify subscribers
                message = self._format_notification_message(queue, new_schedule)
                await self._notify_subscribers(queue, message)
                
                return True
            else:
                logger.debug(f"No changes for queue {queue}")
                return False
                
        except Exception as e:
            logger.error(f"Error checking queue {queue}: {e}", exc_info=True)
            return False
    
    async def check_all_queues(self):
        """Check all queues for updates"""
        logger.info("Starting schedule check for all queues")
        
        for queue in QUEUES:
            await self.check_queue(queue)
            # Small delay between queues
            await asyncio.sleep(0.2)
        
        logger.info("Finished schedule check for all queues")

