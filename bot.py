import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.bot import DefaultBotProperties
from aiogram.enums import ParseMode

from config import Config, load_config
from src.callbacks import callback_handler
from src.handlers import echo, start, get_graphs, notification_settings
from src.services.db import init_db, close_db
from src.services.schedule_checker import ScheduleChecker


logger = logging.getLogger(__name__)

# Global schedule checker instance
schedule_checker: ScheduleChecker = None


async def on_startup(bot: Bot):
    """Initialize services on bot startup"""
    global schedule_checker
    
    logger.info("Initializing database...")
    await init_db()
    
    logger.info("Starting schedule checker...")
    schedule_checker = ScheduleChecker(bot)
    await schedule_checker.start()


async def on_shutdown(bot: Bot):
    """Cleanup on bot shutdown"""
    global schedule_checker
    
    if schedule_checker:
        await schedule_checker.stop()
    
    await close_db()
    logger.info("Bot shutdown complete")


async def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(filename)s:%(lineno)d #%(levelname)-8s "
               "[%(asctime)s] - %(name)s - %(message)s",
    )

    logger.info("Starting bot")

    config: Config = load_config()

    bot_properties = DefaultBotProperties(parse_mode=ParseMode.HTML)
    bot: Bot = Bot(token=config.tg_bot.token, default=bot_properties)
    dp: Dispatcher = Dispatcher()

    dp.include_routers(*(
        start.router,
        callback_handler.router,
        get_graphs.router,
        notification_settings.router,
        #  Other routers

        echo.router,
    ))
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)

    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot stopped")
