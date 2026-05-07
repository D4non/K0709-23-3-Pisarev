"""
Bot Service — Telegram bot for Dating application.
Stage 3: Profile persistence + browsing with ranking and Redis caching.
"""
import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import BotCommand

from app.handlers import start_handler, browse_handler, profile_handler, chat_handler, photos_handler, stats_handler
from shared.config import settings
from shared.logger import setup_logger

logger = setup_logger("bot-service")


async def on_startup(bot: Bot):
    try:
        await bot.set_my_commands([
            BotCommand(command="start", description="Регистрация / обновление анкеты"),
            BotCommand(command="browse", description="Смотреть анкеты"),
            BotCommand(command="profile", description="Моя анкета"),
            BotCommand(command="chats", description="Чаты с совпадениями"),
            BotCommand(command="photos", description="Мои фотографии"),
            BotCommand(command="stats", description="Статистика анкеты"),
            BotCommand(command="delete", description="Удалить анкету"),
        ])
        logger.info("Bot commands registered")
    except Exception as exc:
        logger.warning(f"Failed to set bot commands: {exc}")


async def main():
    logger.info("Starting bot service...")

    bot = Bot(
        token=settings.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )

    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(start_handler.router)
    dp.include_router(browse_handler.router)
    dp.include_router(profile_handler.router)
    dp.include_router(chat_handler.router)
    dp.include_router(photos_handler.router)
    dp.include_router(stats_handler.router)
    dp.startup.register(on_startup)

    logger.info("Bot service initialized successfully")
    await dp.start_polling(bot)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
