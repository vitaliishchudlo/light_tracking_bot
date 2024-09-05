import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.bot import DefaultBotProperties
from aiogram.enums import ParseMode

from config import Config, load_config
from src.callbacks import callback_handler
from src.handlers import echo, start, get_graphs

# from src.services.db import subscriptions_collection, user_notifications_collection, outage_groups_collection
# ToDo Maybe delete this import in future


logger = logging.getLogger(__name__)


async def on_startup(bot: Bot):
    pass
    # TODO Implement here creating of all the graphs images and saving them to the filesystem


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
        #  Other routers

        echo.router,
    ))
    dp.startup.register(on_startup)

    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot stopped")
