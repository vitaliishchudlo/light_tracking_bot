QUEUES = [
    "1.1", "1.2", "2.1", "2.2", "3.1", "3.2",
    "4.1", "4.2", "5.1", "5.2", "6.1", "6.2"
]

# Keep for backward compatibility
GROUPS_NUMBERS = QUEUES

API_BASE_URL = "https://be-svitlo.oe.if.ua/schedule-by-queue"

# Main menu (reply keyboard) button texts
BTN_GRAPHS = "📊 Мої графіки"
BTN_QUEUES = "⚡ Черги"
BTN_NOTIFICATIONS = "🔔 Сповіщення"

# Old button texts - users may still have the old keyboard on screen
OLD_BTN_GRAPHS = "Мої графіки ⚡️"
OLD_BTN_QUEUES = "Налаштування груп 👥"
OLD_BTN_NOTIFICATIONS = "Налаштування сповіщень🔔"

# Reminders: how many minutes before power off / power on a user can be reminded
REMINDER_OFFSETS = [5, 15, 30, 60]
REMINDER_KINDS = ("off", "on")  # off = before shutdown, on = before power returns


def format_offset(minutes: int) -> str:
    """5 -> '5 хв', 60 -> '1 год', 90 -> '1 год 30 хв'"""
    hours, mins = divmod(minutes, 60)
    if hours and mins:
        return f"{hours} год {mins} хв"
    return f"{hours} год" if hours else f"{mins} хв"
