import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from aiogram import Router
from aiogram.types import Message
from aiogram.filters import Command

from app.services.profile_client import ProfileClient
from shared.logger import setup_logger

logger = setup_logger("bot-service.stats")
router = Router()


def _format_stats(stats: dict) -> str:
    matches = stats["matches"]
    likes_r = stats["likes_received"]
    skips_r = stats["skips_received"]
    likes_g = stats["likes_given"]
    photos = stats["photos_count"]
    reg_date = stats["registered_at"]

    total_views = likes_r + skips_r
    like_rate = round(likes_r / total_views * 100) if total_views > 0 else 0

    return (
        "📊 <b>Статистика вашей анкеты</b>\n\n"
        f"❤️  Лайков получено:    <b>{likes_r}</b>\n"
        f"👎  Пропусков получено: <b>{skips_r}</b>\n"
        f"👁  Всего просмотров:   <b>{total_views}</b>\n"
        f"📈  Нравитесь:         <b>{like_rate}%</b> просмотревших\n\n"
        f"💕  Матчей:            <b>{matches}</b>\n"
        f"👆  Лайков отдано:     <b>{likes_g}</b>\n\n"
        f"📸  Фотографий:        <b>{photos}</b>\n"
        f"📅  В сервисе с:       <b>{reg_date}</b>"
    )


@router.message(Command("stats"))
async def cmd_stats(message: Message):
    client = ProfileClient()
    try:
        stats = await client.get_stats(message.from_user.id)
    except Exception as exc:
        logger.error(f"stats: failed to fetch: {exc}")
        await message.answer("⚠️ Сервис временно недоступен. Попробуйте позже.")
        return

    if stats is None:
        await message.answer(
            "😔 У вас нет активной анкеты.\n"
            "Используйте /start чтобы создать её."
        )
        return

    await message.answer(_format_stats(stats), parse_mode="HTML")
