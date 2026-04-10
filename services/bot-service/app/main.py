"""
Bot Service - Telegram bot for Dating application.
Stage 2: Bot interface + User registration via /start.
"""
import sys
import os
from pathlib import Path

# Add project root to sys.path so 'shared' module is discoverable
project_root = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(project_root))

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import BotCommand

from app.handlers import start_handler
from shared.config import settings
from shared.logger import setup_logger

logger = setup_logger("bot-service")


async def on_startup(bot: Bot):
    """Set bot commands on startup."""
    try:
        await bot.set_my_commands([
            BotCommand(command="start", description="Начать использование бота и регистрация"),
        ])
        logger.info("Bot commands registered")
    except Exception as e:
        logger.warning(f"Failed to set bot commands: {e}")


async def main():
    """Main bot entry point."""
    logger.info("Starting bot service...")

    bot = Bot(
        token=settings.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )

    storage = MemoryStorage()
    dp = Dispatcher(storage=storage)

    # Register handlers
    dp.include_router(start_handler.router)

    # Register startup callback
    dp.startup.register(on_startup)

    logger.info("Bot service initialized successfully")
    await dp.start_polling(bot)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
