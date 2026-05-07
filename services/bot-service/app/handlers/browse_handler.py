"""
Browse handler — показ анкет кандидатов с фотографиями.

Если у кандидата есть фото, бот скачивает их через media-service
(Docker-внутренний прокси к MinIO) и отправляет пользователю как
Telegram-фото с подписью. Если фото нет или скачать не удалось —
показывает текстовую карточку.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from aiogram import Router, F, Bot
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    BufferedInputFile,
)
from aiogram.filters import Command
from aiogram.filters.callback_data import CallbackData

from app.services.profile_client import ProfileClient
from app.services.media_client import MediaClient
from shared.logger import setup_logger

logger = setup_logger("bot-service.browse")
router = Router()


class InteractionCb(CallbackData, prefix="interact"):
    action: str           # "like" | "skip" | "stop"
    candidate_tg_id: int


def _keyboard(candidate_tg_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="❤️",
                    callback_data=InteractionCb(action="like", candidate_tg_id=candidate_tg_id).pack(),
                ),
                InlineKeyboardButton(
                    text="👎",
                    callback_data=InteractionCb(action="skip", candidate_tg_id=candidate_tg_id).pack(),
                ),
            ],
            [
                InlineKeyboardButton(
                    text="🚫 Стоп",
                    callback_data=InteractionCb(action="stop", candidate_tg_id=candidate_tg_id).pack(),
                ),
            ],
        ]
    )


def _format_profile(data: dict) -> str:
    gender_icon = "♂️" if data.get("gender") == "male" else "♀️"
    interests = data.get("interests") or []
    interests_str = ", ".join(interests) if interests else "не указаны"
    bio = data.get("bio") or "не указано"
    photo_note = f"📸 {len(data.get('photos', []))} фото" if data.get("photos") else ""
    return (
        f"<b>{data['name']}, {data['age']}</b> {gender_icon}\n"
        f"📍 {data['city']}\n"
        f"🎯 Интересы: {interests_str}\n"
        f"📝 {bio}"
        + (f"\n{photo_note}" if photo_note else "")
    )


async def _send_candidate(bot: Bot, chat_id: int, candidate: dict) -> None:
    """
    Send candidate card to chat.
    Tries to attach the primary photo; falls back to text-only on any error.
    """
    text = _format_profile(candidate)
    keyboard = _keyboard(candidate["telegram_id"])
    photos = candidate.get("photos", [])

    # Pick primary photo; fall back to first available
    primary = next((p for p in photos if p.get("is_primary")), photos[0] if photos else None)

    if primary and primary.get("object_key"):
        media = MediaClient()
        try:
            photo_bytes = await media.get_photo(primary["object_key"])
            await bot.send_photo(
                chat_id=chat_id,
                photo=BufferedInputFile(photo_bytes, filename="photo.jpg"),
                caption=text,
                reply_markup=keyboard,
                parse_mode="HTML",
            )
            return
        except Exception as exc:
            logger.warning(f"Could not load photo for candidate {candidate['telegram_id']}: {exc}")

    # Text fallback
    await bot.send_message(chat_id=chat_id, text=text, reply_markup=keyboard, parse_mode="HTML")


# ─── /browse ──────────────────────────────────────────────────────────────────

@router.message(Command("browse"))
async def cmd_browse(message: Message):
    client = ProfileClient()
    try:
        candidate = await client.get_recommendation(message.from_user.id)
    except Exception as exc:
        logger.error(f"browse: failed to fetch recommendation: {exc}")
        await message.answer("⚠️ Сервис временно недоступен. Попробуйте позже.")
        return

    if candidate is None:
        await message.answer(
            "😔 Подходящих анкет пока нет.\n"
            "Попробуй позже или пригласи друзей! 👫"
        )
        return

    await _send_candidate(message.bot, message.chat.id, candidate)


# ─── callbacks ────────────────────────────────────────────────────────────────

@router.callback_query(InteractionCb.filter(F.action == "stop"))
async def cb_stop(callback: CallbackQuery):
    try:
        await callback.message.edit_text(
            "🚫 Просмотр остановлен.\n"
            "Используй /browse чтобы продолжить."
        )
    except Exception:
        await callback.message.answer("🚫 Просмотр остановлен.")
    await callback.answer()


@router.callback_query(InteractionCb.filter(F.action.in_({"like", "skip"})))
async def cb_interaction(callback: CallbackQuery, callback_data: InteractionCb):
    client = ProfileClient()
    viewer_id = callback.from_user.id
    candidate_id = callback_data.candidate_tg_id
    action = callback_data.action

    try:
        result = await client.record_interaction(
            viewer_telegram_id=viewer_id,
            candidate_telegram_id=candidate_id,
            action=action,
        )
    except Exception as exc:
        logger.error(f"interaction: {exc}")
        await callback.answer("⚠️ Ошибка. Попробуйте ещё раз.")
        return

    if action == "like":
        if result.get("is_match"):
            match_name = result.get("candidate_name", "пользователь")
            viewer_name = result.get("viewer_name", "пользователь")
            await callback.message.answer(f"🎉 Взаимная симпатия с <b>{match_name}</b>!")
            try:
                await callback.bot.send_message(
                    chat_id=candidate_id,
                    text=f"🎉 Взаимная симпатия с <b>{viewer_name}</b>!",
                )
            except Exception as exc:
                logger.warning(f"Failed to send match notification to {candidate_id}: {exc}")
        else:
            try:
                await callback.bot.send_message(
                    chat_id=candidate_id,
                    text="❤️ Кто-то заинтересовался твоей анкетой!\n"
                         "Используй /browse — вдруг это взаимно 😊",
                )
            except Exception as exc:
                logger.warning(f"Failed to send like notification to {candidate_id}: {exc}")

    try:
        next_candidate = await client.get_recommendation(viewer_id)
    except Exception as exc:
        logger.error(f"browse: next recommendation failed: {exc}")
        await callback.message.answer("⚠️ Не удалось загрузить следующую анкету.")
        await callback.answer()
        return

    if next_candidate is None:
        try:
            await callback.message.edit_text("😔 Анкеты закончились.\nЗагляни позже!")
        except Exception:
            await callback.message.answer("😔 Анкеты закончились.\nЗагляни позже!")
    else:
        # Delete old card (could be photo or text) and send fresh one
        try:
            await callback.message.delete()
        except Exception:
            pass
        await _send_candidate(callback.bot, callback.message.chat.id, next_candidate)

    await callback.answer()
