import asyncio
import logging
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime, timedelta
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from src.services.api_client import ScheduleAPI
from src.services.db import get_schedules_collection, subscriptions_collection, user_settings_collection
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
        
        # Verify schedules_collection is initialized
        schedules_collection = get_schedules_collection()
        if schedules_collection is None:
            logger.error("Cannot start schedule checker - schedules_collection is not initialized!")
            raise RuntimeError("schedules_collection is not initialized. Call init_db() first.")
        
        self.is_running = True
        # Run every 5 minutes to reduce API load
        self.scheduler.add_job(
            self.check_all_queues,
            trigger=IntervalTrigger(minutes=5),
            id='check_schedules',
            replace_existing=True
        )
        self.scheduler.start()
        logger.info("Schedule checker started successfully")
    
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
            # Keep dates even if queues_data is empty (cancelled schedule)
            # This allows us to detect when a schedule is cancelled
            
            shutdowns = []
            if queues_data:  # Only process if there are shutdowns
                for shutdown in queues_data:
                    shutdowns.append({
                        'from': shutdown.get('from'),
                        'to': shutdown.get('to'),
                        'shutdownHours': shutdown.get('shutdownHours'),
                        'status': shutdown.get('status')
                    })
            
            # Always add the date, even if shutdowns is empty (cancelled)
            normalized[event_date] = {
                'shutdowns': shutdowns,
                'createdAt': item.get('createdAt'),
                'scheduleApprovedSince': item.get('scheduleApprovedSince')
            }
        
        return normalized
    
    async def _has_changes(self, queue: str, old_schedule: Dict[str, Any], new_schedule: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """
        Check if schedule has changed
        
        Args:
            queue: Queue number
            old_schedule: Previous schedule state
            new_schedule: New schedule state
            
        Returns:
            Tuple of (has_changes, new_date_notification, cancelled_dates)
            - has_changes: True if there are changes in actual schedule data
            - new_date_notification: Date string if new date appeared (e.g., tomorrow) that we haven't shown today, None otherwise
            - cancelled_dates: Set of dates that were cancelled (had shutdowns, now empty)
        """
        # First time - save schedule but don't notify (return False to skip notification)
        # This prevents spamming users on first run
        # BUT: if there are new dates with actual shutdowns, we should notify
        if not old_schedule or len(old_schedule) == 0:
            logger.info(f"First time checking this queue or empty old schedule. Old: {old_schedule}, New dates: {list(new_schedule.keys())}")
            
            # Check if there are new dates with actual shutdowns - if yes, notify
            if new_schedule and len(new_schedule) > 0:
                for date, date_data in new_schedule.items():
                    shutdowns = date_data.get('shutdowns', [])
                    if len(shutdowns) > 0:
                        # Found a date with actual shutdowns - notify about it
                        shown_dates = await self._get_shown_dates_today(queue)
                        if date not in shown_dates:
                            logger.info(f"First time but found new date {date} with shutdowns - will notify")
                            return True, date, set()
            
            # No new dates with shutdowns, or all already shown - don't notify
            return False, None, set()
        
        # Compare by event dates and shutdowns
        old_dates = set(old_schedule.keys())
        new_dates = set(new_schedule.keys())
        
        # Check for new dates (e.g., tomorrow's schedule appeared)
        new_date_added = new_dates - old_dates
        new_date_to_notify = None
        
        if new_date_added:
            # Check if we already showed this date today
            shown_dates = await self._get_shown_dates_today(queue)
            for new_date in sorted(new_date_added):
                # Only notify if the new date has actual shutdowns (not empty/cancelled)
                new_date_data = new_schedule.get(new_date, {})
                new_date_shutdowns = new_date_data.get('shutdowns', [])
                
                if new_date not in shown_dates and len(new_date_shutdowns) > 0:
                    logger.info(f"New date appeared for {queue}: {new_date} - will notify")
                    new_date_to_notify = new_date
                    break  # Only notify about the first new date we haven't shown
                elif len(new_date_shutdowns) == 0:
                    logger.debug(f"New date {new_date} appeared but is empty (cancelled) - skipping notification")
        
        # Check if shutdowns changed for existing dates
        has_existing_changes = False
        cancelled_dates = set()  # Dates that were cancelled (had shutdowns, now empty)
        
        # Check dates that exist in both old and new schedules
        common_dates = new_dates & old_dates
        logger.debug(f"Checking {len(common_dates)} common dates for changes: {list(common_dates)[:3]}")
        
        for date in common_dates:
            old_date_data = old_schedule.get(date, {})
            new_date_data = new_schedule.get(date, {})
            
            old_shutdowns = old_date_data.get('shutdowns', [])
            new_shutdowns = new_date_data.get('shutdowns', [])
            
            logger.debug(f"Date {date}: old_shutdowns={len(old_shutdowns)}, new_shutdowns={len(new_shutdowns)}")
            
            # Check if schedule was cancelled (had shutdowns, now empty)
            if len(old_shutdowns) > 0 and len(new_shutdowns) == 0:
                logger.info(f"Schedule cancelled for {date}: had {len(old_shutdowns)} shutdowns, now empty")
                cancelled_dates.add(date)
                has_existing_changes = True
                continue  # Don't check other changes for cancelled dates
            
            # Compare shutdowns count
            if len(old_shutdowns) != len(new_shutdowns):
                logger.info(f"Shutdown count changed for {date}: old={len(old_shutdowns)}, new={len(new_shutdowns)}")
                has_existing_changes = True
                # Don't break - continue checking other dates for changes
            
            # Compare each shutdown by creating a set of (from, to) tuples
            old_shutdown_set = {(sh.get('from'), sh.get('to')) for sh in old_shutdowns}
            new_shutdown_set = {(sh.get('from'), sh.get('to')) for sh in new_shutdowns}
            
            if old_shutdown_set != new_shutdown_set:
                logger.info(f"Shutdown times changed for {date}: old={old_shutdown_set}, new={new_shutdown_set}")
                has_existing_changes = True
                # Don't break - continue checking other dates for changes
        
        # Check if all schedules were removed (old had dates, new is empty)
        # Empty array [] from API means no schedules exist (not cancelled, just absent)
        # We should NOT notify about this - just silently update the database
        if len(old_dates) > 0 and len(new_dates) == 0:
            logger.info(f"Empty schedule received ([]), old had {len(old_dates)} dates - silently updating DB, no notification")
            # Don't notify - empty [] means no schedules, not cancellation
            return False, None, set()
        
        # Check if dates were removed (but not if new dates were added)
        # Only notify if removed dates are in the future (not past dates that naturally expired)
        elif old_dates != new_dates and not new_date_added:
            removed_dates = old_dates - new_dates
            if removed_dates:
                # Check if removed dates are in the past (naturally expired)
                now = datetime.now()
                all_removed_are_past = True
                for removed_date in removed_dates:
                    date_obj = self._parse_date(removed_date)
                    if date_obj:
                        # Check if the date is today or in the future
                        # If date is today, check if it's past midnight (next day)
                        date_only = date_obj.date()
                        today = now.date()
                        if date_only >= today:
                            all_removed_are_past = False
                            break
                        # If date is yesterday or earlier, it's naturally expired
                    else:
                        # Can't parse date, assume it's not past
                        all_removed_are_past = False
                
                if not all_removed_are_past:
                    logger.info(f"Schedule dates changed: old={old_dates}, new={new_dates}")
                    has_existing_changes = True
                else:
                    logger.debug(f"Removed dates {removed_dates} are in the past - not notifying (natural expiration)")
        
        # Return True if we have new date to notify OR existing changes
        if new_date_to_notify or has_existing_changes:
            return True, new_date_to_notify, cancelled_dates
        
        # Don't notify on scheduleApprovedSince changes alone - only on actual schedule changes
        logger.debug("No changes detected in schedule data")
        return False, None, set()
    
    def _parse_date(self, date_str: str) -> Optional[datetime]:
        """Parse date string in format DD.MM.YYYY"""
        try:
            return datetime.strptime(date_str, "%d.%m.%Y")
        except ValueError:
            logger.warning(f"Failed to parse date: {date_str}")
            return None
    
    def _parse_time(self, time_str: str):
        """Parse time string in format HH:MM, returns time object"""
        try:
            return datetime.strptime(time_str, "%H:%M").time()
        except ValueError:
            logger.warning(f"Failed to parse time: {time_str}")
            return None
    
    def _is_shutdown_past(self, event_date: str, shutdown_from: str, shutdown_to: str) -> bool:
        """Check if shutdown is in the past (ended)"""
        try:
            date_obj = self._parse_date(event_date)
            if not date_obj:
                return False
            
            from_time = self._parse_time(shutdown_from)
            to_time = self._parse_time(shutdown_to)
            
            if not from_time or not to_time:
                return False
            
            # Create datetime for shutdown end time
            shutdown_end = datetime.combine(date_obj.date(), to_time)
            
            # Handle case where to_time is 00:00 (means it ends at midnight, next day)
            if shutdown_to == "00:00":
                shutdown_end += timedelta(days=1)
            
            now = datetime.now()
            # Shutdown is past only if it has ENDED (shutdown_end < now)
            # If shutdown_end == now or shutdown_end > now, it's still active or hasn't started
            is_past = shutdown_end < now
            logger.debug(f"Shutdown {event_date} {shutdown_from}-{shutdown_to}: end={shutdown_end}, now={now}, is_past={is_past}")
            return is_past
        except Exception as e:
            logger.error(f"Error checking if shutdown is past: {e}", exc_info=True)
            return False
    
    async def _get_shown_dates_today(self, queue: str) -> set:
        """Get dates that were shown to users today"""
        schedules_collection = get_schedules_collection()
        if schedules_collection is None:
            return set()
        
        try:
            doc = await schedules_collection.find_one({"queue": queue})
            if not doc:
                return set()
            
            shown_dates = doc.get('shownDates', [])
            today = datetime.now().strftime("%d.%m.%Y")
            
            # Return only dates that were shown today
            today_shown = {item['date'] for item in shown_dates if item.get('shownDate') == today}
            return today_shown
        except Exception as e:
            logger.error(f"Error getting shown dates for {queue}: {e}")
            return set()
    
    async def _mark_date_as_shown(self, queue: str, date: str):
        """Mark a date as shown today"""
        schedules_collection = get_schedules_collection()
        if schedules_collection is None:
            return
        
        try:
            today = datetime.now().strftime("%d.%m.%Y")
            
            # Get current shown dates
            doc = await schedules_collection.find_one({"queue": queue})
            shown_dates = doc.get('shownDates', []) if doc else []
            
            # Remove old entries for this date
            shown_dates = [item for item in shown_dates if item.get('date') != date]
            
            # Add new entry
            shown_dates.append({
                'date': date,
                'shownDate': today
            })
            
            # Update database
            await schedules_collection.update_one(
                {"queue": queue},
                {"$set": {"shownDates": shown_dates}},
                upsert=True
            )
            logger.info(f"Marked date {date} as shown for queue {queue}")
        except Exception as e:
            logger.error(f"Error marking date as shown for {queue}: {e}")
    
    async def _get_stored_schedule(self, queue: str) -> Optional[Dict[str, Any]]:
        """Get stored schedule from database"""
        schedules_collection = get_schedules_collection()
        if schedules_collection is None:
            logger.warning("schedules_collection is not initialized - cannot retrieve stored schedule")
            return None
        
        logger.debug(f"Getting stored schedule for {queue}, collection exists: {schedules_collection is not None}")
            
        try:
            doc = await schedules_collection.find_one({"queue": queue})
            logger.debug(f"Database query result for {queue}: found={doc is not None}")
            
            if doc:
                schedule = doc.get('schedule', {})
                logger.debug(f"Found doc for {queue}, schedule type: {type(schedule)}, keys: {list(schedule.keys()) if isinstance(schedule, dict) else 'not a dict'}")
                
                if schedule and isinstance(schedule, dict) and len(schedule) > 0:
                    logger.info(f"Retrieved stored schedule for {queue}: {len(schedule)} dates - {list(schedule.keys())[:3]}")
                    return schedule
                elif isinstance(schedule, dict) and len(schedule) == 0:
                    # Empty schedule is valid (means no schedules exist)
                    logger.debug(f"Retrieved empty schedule for {queue} (no schedules exist)")
                    return None
                else:
                    logger.warning(f"Stored schedule for {queue} is invalid: type={type(schedule)}, value={schedule}")
                    return None
            logger.info(f"No stored schedule found for {queue} in database - document does not exist")
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
            logger.debug(f"Saving schedule for {queue}: {len(schedule)} dates - {list(schedule.keys())[:3]}")
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
                logger.info(f"✅ Created new schedule record for {queue} with {len(schedule)} dates, upserted_id={result.upserted_id}")
            elif result.modified_count > 0:
                logger.info(f"✅ Updated schedule for {queue} with {len(schedule)} dates, matched={result.matched_count}")
            else:
                logger.debug(f"Schedule for {queue} unchanged, matched={result.matched_count}")
            
            # Verify it was saved
            verify_doc = await schedules_collection.find_one({"queue": queue})
            if verify_doc and 'schedule' in verify_doc:
                schedule_data = verify_doc.get('schedule', {})
                logger.debug(f"Verified: schedule saved for {queue}, has {len(schedule_data)} dates")
            else:
                logger.error(f"❌ Failed to verify save for {queue} - doc={verify_doc}")
        except Exception as e:
            logger.error(f"Error saving schedule for {queue}: {e}", exc_info=True)
    
    def _format_notification_message(self, queue: str, schedule: Dict[str, Any], new_date: Optional[str] = None, cancelled_dates: Optional[set] = None) -> str:
        """
        Format notification message for users
        
        Args:
            queue: Queue number
            schedule: Schedule data
            new_date: Optional new date that appeared (e.g., tomorrow)
            cancelled_dates: Set of dates that were cancelled (had shutdowns, now empty)
            
        Returns:
            Formatted message
        """
        if cancelled_dates is None:
            cancelled_dates = set()
        
        # Check if all dates in schedule are cancelled
        sorted_dates = sorted(schedule.keys())
        all_cancelled = all(date in cancelled_dates for date in sorted_dates) and len(sorted_dates) > 0
        
        if all_cancelled:
            # All dates are cancelled - show cancellation message
            message_parts = [f"🚫 <b>Скасовано графік для черги <u>{queue}</u></b>"]
        elif new_date:
            message_parts = [f"🔔 <b>З'явився графік на <u>{new_date}</u> для черги <u>{queue}</u></b>"]
        else:
            message_parts = [f"🔔 <b>Зміни у графіку для черги <u>{queue}</u></b> ❗"]

        # Sort dates
        for date in sorted_dates:
            date_data = schedule[date]
            shutdowns = date_data.get('shutdowns', [])
            is_cancelled = date in cancelled_dates
            
            if is_cancelled:
                # Show cancellation message for this date
                message_parts.append(f"\n\n📅 {date}")
                message_parts.append(f"   💡 <b>Графік скасовано</b> ⚡️")
            elif shutdowns:
                message_parts.append(f"\n\n📅 {date}\n")
                for shutdown in shutdowns:
                    hours = shutdown.get('shutdownHours', '')
                    from_time = shutdown.get('from', '')
                    to_time = shutdown.get('to', '')
                    
                    if hours:
                        # Check if shutdown is in the past
                        is_past = self._is_shutdown_past(date, from_time, to_time)
                        if is_past:
                            message_parts.append(f"   🔴️ <s> {hours} </s>")
                        else:
                            message_parts.append(f"   🔴️ {hours}")
            
            approved_since = date_data.get('scheduleApprovedSince')
            if approved_since:
                message_parts.append(f"\n📌 Оновлено: {approved_since}")
        
        return "\n".join(message_parts)
    
    def _get_notification_settings(self, user_id: int) -> tuple[bool, bool]:
        """
        Get user notification settings
        
        Args:
            user_id: Telegram user ID
            
        Returns:
            Tuple of (should_notify, disable_notification)
            - should_notify: True if notification should be sent, False otherwise
            - disable_notification: True if notification should be silent, False otherwise
        """
        # Get user settings
        user_settings = user_settings_collection.find_one({"id_telegram": user_id})
        notification_mode = user_settings.get('notification_mode', 'always') if user_settings else 'always'
        
        # If disabled, never notify
        if notification_mode == 'disabled':
            return False, False
        
        # If always, always notify normally
        if notification_mode == 'always':
            return True, False
        
        # For night modes, check if current time is within quiet hours
        # If yes - send silently, if no - send with sound
        # Night modes are: 22-06, 22-08, 00-06, 00-08, 00-10
        now = datetime.now()
        current_hour = now.hour
        current_minute = now.minute
        current_time_minutes = current_hour * 60 + current_minute
        
        # Parse mode (e.g., "22-06" means from 22:00 to 06:00)
        try:
            start_hour_str, end_hour_str = notification_mode.split('-')
            start_hour = int(start_hour_str)
            end_hour = int(end_hour_str)
            
            start_time_minutes = start_hour * 60
            end_time_minutes = end_hour * 60
            
            # Check if current time is within quiet hours
            is_quiet_hours = False
            
            # Handle overnight periods (e.g., 22:00 to 06:00)
            if start_hour > end_hour:
                # Overnight: check if current time is after start OR before end
                if current_time_minutes >= start_time_minutes or current_time_minutes < end_time_minutes:
                    is_quiet_hours = True
            else:
                # Same day: check if current time is between start and end
                if start_time_minutes <= current_time_minutes < end_time_minutes:
                    is_quiet_hours = True
            
            # If in quiet hours, send silently; otherwise send with sound
            if is_quiet_hours:
                return True, True  # Send notification silently during quiet hours
            else:
                return True, False  # Send notification with sound outside quiet hours
        except (ValueError, AttributeError):
            # Invalid mode format, default to always notify
            logger.warning(f"Invalid notification mode '{notification_mode}' for user {user_id}, defaulting to always")
            return True, False
    
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
        skipped_count = 0
        failed_count = 0
        
        for subscriber in subscribers:
            try:
                user_id = subscriber.get('id_telegram')
                if user_id:
                    # Check if we should notify this user based on their settings
                    should_notify, disable_notification = self._get_notification_settings(user_id)
                    if not should_notify:
                        skipped_count += 1
                        continue
                    
                    await self.bot.send_message(
                        chat_id=user_id,
                        text=message,
                        parse_mode='HTML',
                        disable_notification=disable_notification
                    )
                    notified_count += 1
                    # Small delay to avoid rate limiting
                    await asyncio.sleep(0.05)
            except Exception as e:
                failed_count += 1
                user_id = subscriber.get('id_telegram', 'unknown')
                logger.error(f"Failed to notify user {user_id} about queue {queue}: {e}")
        
        logger.info(f"Notified {notified_count} subscribers about queue {queue} (skipped: {skipped_count}, failed: {failed_count})")
    
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
            # Handle empty array response (no schedules for today/tomorrow)
            # Empty array [] means no schedules exist (not cancelled, just absent)
            # We will silently update the database without notifications
            if schedule_data == []:
                logger.info(f"Empty schedule received for queue {queue} - no schedules exist")
                # Normalize empty schedule (will result in empty dict)
                new_schedule = {}
            elif not schedule_data:
                logger.warning(f"No data received for queue {queue}")
                return False
            else:
                # Normalize the schedule
                new_schedule = self._normalize_schedule(schedule_data, queue)
            logger.debug(f"Fetched schedule for {queue}: {len(new_schedule)} dates")
            
            # Get stored schedule
            old_schedule = await self._get_stored_schedule(queue)
            if old_schedule:
                logger.info(f"Retrieved old schedule for {queue}: {len(old_schedule)} dates - {list(old_schedule.keys())[:3]}")
            else:
                logger.warning(f"No old schedule found for {queue} - this is first time or DB issue")
            
            # Get the latest approved since timestamp from the new schedule
            latest_approved = None
            for date, date_data in new_schedule.items():
                approved = date_data.get('scheduleApprovedSince')
                if approved:
                    if not latest_approved or approved > latest_approved:
                        latest_approved = approved
            
            # Check for changes
            has_changes, new_date, cancelled_dates = await self._has_changes(queue, old_schedule, new_schedule)
            
            # Always save the latest schedule to database
            await self._save_schedule(queue, new_schedule, latest_approved)
            
            # Only notify if there are actual changes
            if has_changes:
                # Check if there are changes in existing dates (excluding cancelled ones)
                old_dates = set(old_schedule.keys()) if old_schedule else set()
                new_dates = set(new_schedule.keys())
                existing_dates_changed = False
                changed_dates = set()
                
                for date in new_dates & old_dates:
                    # Skip cancelled dates - they're handled separately
                    if date in cancelled_dates:
                        continue
                    
                    old_date_data = old_schedule.get(date, {})
                    new_date_data = new_schedule.get(date, {})
                    old_shutdowns = old_date_data.get('shutdowns', [])
                    new_shutdowns = new_date_data.get('shutdowns', [])
                    old_shutdown_set = {(sh.get('from'), sh.get('to')) for sh in old_shutdowns}
                    new_shutdown_set = {(sh.get('from'), sh.get('to')) for sh in new_shutdowns}
                    if old_shutdown_set != new_shutdown_set or len(old_shutdowns) != len(new_shutdowns):
                        existing_dates_changed = True
                        changed_dates.add(date)
                
                # Prepare schedule to show in notification
                if cancelled_dates:
                    logger.info(f"Schedule cancelled for {queue} on dates: {cancelled_dates}")
                    # Show cancelled dates - use old_schedule data since new_schedule might be empty
                    cancelled_schedule = {}
                    for date in cancelled_dates:
                        # Try to get from new_schedule first, fallback to old_schedule
                        if date in new_schedule:
                            cancelled_schedule[date] = new_schedule[date]
                        elif old_schedule and date in old_schedule:
                            # Use old schedule data but mark as cancelled (empty shutdowns)
                            cancelled_schedule[date] = {
                                **old_schedule[date],
                                'shutdowns': []  # Mark as cancelled
                            }
                    # Also include changed dates if any
                    for date in changed_dates:
                        if date in new_schedule:
                            cancelled_schedule[date] = new_schedule[date]
                    message = self._format_notification_message(queue, cancelled_schedule, None, cancelled_dates)
                elif new_date:
                    logger.info(f"New date appeared for {queue}: {new_date} - notifying subscribers")
                    # Mark this date as shown
                    await self._mark_date_as_shown(queue, new_date)
                    
                    if existing_dates_changed:
                        # Show both new date and changed existing dates
                        notification_schedule = {new_date: new_schedule[new_date]}
                        for date in changed_dates:
                            notification_schedule[date] = new_schedule[date]
                        message = self._format_notification_message(queue, notification_schedule, new_date, cancelled_dates)
                    else:
                        # Show only the new date
                        new_date_schedule = {new_date: new_schedule[new_date]}
                        message = self._format_notification_message(queue, new_date_schedule, new_date, cancelled_dates)
                elif existing_dates_changed:
                    logger.info(f"Changes in existing dates for {queue} - notifying subscribers")
                    # Show only changed dates
                    changed_schedule = {date: new_schedule[date] for date in changed_dates}
                    message = self._format_notification_message(queue, changed_schedule, None, cancelled_dates)
                else:
                    # Fallback - show all new schedule
                    message = self._format_notification_message(queue, new_schedule, None, cancelled_dates)
                
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
            # Delay between API calls for different queues to avoid bursts
            await asyncio.sleep(10)
        
        logger.info("Finished schedule check for all queues")

