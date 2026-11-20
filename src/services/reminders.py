"""Reminders N minutes before power off / power on.

Runs every minute. For every user who enabled reminders, takes the schedules of the
queues they are subscribed to and sends a reminder when "event time - N minutes" has come.
Each reminder is sent at most once: a record is stored in `reminders_sent` before sending.
"""
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Callable, Dict, List, Tuple

from aiogram import Bot
from pymongo.errors import DuplicateKeyError

from src.constants import REMINDER_OFFSETS, format_offset
from src.services.db import (
    get_schedules_collection,
    get_subscriptions_collection,
    get_user_settings_collection,
)

logger = logging.getLogger(__name__)

# How late a reminder may still be sent (e.g. bot restart or a slow minute)
GRACE = timedelta(minutes=3)
# How long sent-reminder records are kept (MongoDB removes them automatically)
SENT_TTL_SECONDS = 2 * 24 * 3600

Interval = Tuple[datetime, datetime]


def _get_sent_collection():
    schedules = get_schedules_collection()
    return schedules.database["reminders_sent"] if schedules is not None else None


async def init_reminders_storage():
    """Index that auto-deletes old sent-reminder records"""
    sent = _get_sent_collection()
    if sent is not None:
        await sent.create_index("created_at", expireAfterSeconds=SENT_TTL_SECONDS)


def build_intervals(schedule: Dict) -> List[Interval]:
    """All shutdowns of a queue as (start, end) datetimes, sorted, with touching ones merged.

    Merging matters for reminders: 15:30-19:00 + 19:00-21:00 is one outage, so there
    must be no "power is coming back at 19:00" reminder. "00:00" as end means midnight.
    """
    intervals: List[Interval] = []
    for date_str, data in (schedule or {}).items():
        try:
            day = datetime.strptime(date_str, "%d.%m.%Y")
        except ValueError:
            continue
        for shutdown in (data or {}).get("shutdowns", []):
            try:
                f_h, f_m = map(int, shutdown["from"].split(":"))
                t_h, t_m = map(int, shutdown["to"].split(":"))
            except (KeyError, ValueError, AttributeError):
                continue
            start = day + timedelta(hours=f_h, minutes=f_m)
            end = day + timedelta(hours=t_h, minutes=t_m)
            if end <= start:  # ends at midnight (or crosses it)
                end += timedelta(days=1)
            intervals.append((start, end))

    intervals.sort()
    merged: List[Interval] = []
    for start, end in intervals:
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


def _duration(start: datetime, end: datetime) -> str:
    return format_offset(int((end - start).total_seconds() // 60))


def _hhmm(dt: datetime) -> str:
    return dt.strftime("%H:%M")


def build_message(kind: str, minutes: int, event_time: datetime, items: List[Tuple[str, Interval]]) -> str:
    """One reminder message; queues with the same outage are joined in one line"""
    by_interval: Dict[Interval, List[str]] = {}
    for queue, interval in items:
        by_interval.setdefault(interval, []).append(queue)

    if kind == "off":
        lines = [f"⏰ <b>Через {format_offset(minutes)} вимкнуть світло</b> (о {_hhmm(event_time)})"]
        icon = "🔴"
    else:
        lines = [f"💡 <b>Через {format_offset(minutes)} увімкнуть світло</b> (о {_hhmm(event_time)})"]
        icon = "🟢"

    for (start, end), queues in sorted(by_interval.items()):
        label = "Черга" if len(queues) == 1 else "Черги"
        queues_text = ", ".join(sorted(queues))
        lines.append(
            f"<blockquote>{icon} {label} {queues_text} · "
            f"{_hhmm(start)} - {_hhmm(end)} – (<i>на {_duration(start, end)}</i>)</blockquote>"
        )
    return "\n".join(lines)


def collect_due(
    now: datetime,
    user_reminders: Dict[int, Dict[str, set]],
    user_queues: Dict[int, set],
    queue_intervals: Dict[str, List[Interval]],
) -> Dict[Tuple[int, str, datetime, int], List[Tuple[str, Interval]]]:
    """Which reminders are due right now: {(user, kind, event_time, minutes): [(queue, interval)]}"""
    due: Dict[Tuple[int, str, datetime, int], List[Tuple[str, Interval]]] = {}
    for user_id, reminders in user_reminders.items():
        for queue in user_queues.get(user_id, ()):
            for interval in queue_intervals.get(queue, ()):
                for kind, event_time in (("off", interval[0]), ("on", interval[1])):
                    if event_time <= now:
                        continue
                    for minutes in reminders.get(kind, ()):
                        remind_at = event_time - timedelta(minutes=minutes)
                        if remind_at <= now < remind_at + GRACE:
                            due.setdefault((user_id, kind, event_time, minutes), []).append((queue, interval))
    return due


async def send_due_reminders(bot: Bot, get_notification_settings: Callable[[int], Tuple[bool, bool]]):
    """Job body: find due reminders and send them"""
    schedules = get_schedules_collection()
    sent = _get_sent_collection()
    if schedules is None or sent is None:
        return

    now = datetime.now()
    loop = asyncio.get_running_loop()

    def load_users():
        settings = get_user_settings_collection().find(
            {"$or": [{"reminders_off.0": {"$exists": True}}, {"reminders_on.0": {"$exists": True}}]}
        )
        reminders = {
            s["id_telegram"]: {
                "off": {m for m in s.get("reminders_off", []) if m in REMINDER_OFFSETS},
                "on": {m for m in s.get("reminders_on", []) if m in REMINDER_OFFSETS},
            }
            for s in settings
        }
        queues: Dict[int, set] = {}
        if reminders:
            for sub in get_subscriptions_collection().find({"id_telegram": {"$in": list(reminders)}}):
                queue = sub.get("queue") or sub.get("group_number")
                if queue:
                    queues.setdefault(sub["id_telegram"], set()).add(queue)
        return reminders, queues

    try:
        user_reminders, user_queues = await loop.run_in_executor(None, load_users)
    except Exception as e:
        logger.error(f"Reminders: cannot load users: {e}")
        return
    if not user_reminders:
        return

    needed_queues = set().union(*user_queues.values()) if user_queues else set()
    queue_intervals = {}
    async for doc in schedules.find({"queue": {"$in": list(needed_queues)}}):
        queue_intervals[doc["queue"]] = build_intervals(doc.get("schedule", {}))

    due = collect_due(now, user_reminders, user_queues, queue_intervals)
    for (user_id, kind, event_time, minutes), items in due.items():
        should_notify, silent = get_notification_settings(user_id)
        if not should_notify:
            continue

        key = f"{user_id}|{kind}|{event_time:%Y%m%d%H%M}|{minutes}"
        try:
            # Mark first, send second: a reminder is never sent twice
            await sent.insert_one({"_id": key, "created_at": datetime.utcnow()})
        except DuplicateKeyError:
            continue

        try:
            await bot.send_message(
                chat_id=user_id,
                text=build_message(kind, minutes, event_time, items),
                parse_mode="HTML",
                disable_notification=silent,
            )
            logger.info(f"Reminder sent: {key}")
            await asyncio.sleep(0.05)
        except Exception as e:
            logger.error(f"Failed to send reminder {key}: {e}")
