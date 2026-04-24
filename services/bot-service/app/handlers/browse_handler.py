import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from aiogram.filters.callback_data import CallbackData

from app.services.profile_client import ProfileClient
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
    return (
        f"<b>{data['name']}, {data['age']}</b> {gender_icon}\n"
        f"📍 {data['city']}\n"
        f"🎯 Интересы: {interests_str}\n"
        f"📝 {bio}"
    )


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

    await message.answer(
        _format_profile(candidate),
        reply_markup=_keyboard(candidate["telegram_id"]),
    )


@router.callback_query(InteractionCb.filter(F.action == "stop"))
async def cb_stop(callback: CallbackQuery):
    await callback.message.edit_text(
        "🚫 Просмотр остановлен.\n"
        "Используй /browse чтобы продолжить."
    )
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
                    text="❤️ Кто-то заинтересовался твоей анкетой!\nИспользуй /browse, чтобы смотреть анкеты — вдруг это взаимно 😊",
                )
            except Exception as exc:
                logger.warning(f"Failed to send like notification to {candidate_id}: {exc}")

    try:
        next_candidate = await client.get_recommendation(viewer_id)
    except Exception as exc:
        logger.error(f"browse: next recommendation failed: {exc}")
        await callback.message.edit_text("⚠️ Не удалось загрузить следующую анкету.")
        await callback.answer()
        return

    if next_candidate is None:
        await callback.message.edit_text(
            "😔 Анкеты закончились.\n"
            "Загляни позже — появятся новые!"
        )
    else:
        await callback.message.edit_text(
            _format_profile(next_candidate),
            reply_markup=_keyboard(next_candidate["telegram_id"]),
        )

    await callback.answer()
