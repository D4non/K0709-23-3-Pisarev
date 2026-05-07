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
    InputMediaPhoto,
)
from aiogram.filters import Command
from aiogram.filters.callback_data import CallbackData

from app.services.profile_client import ProfileClient
from app.services.media_client import MediaClient
from shared.logger import setup_logger

logger = setup_logger("bot-service.profile")
router = Router()


class DeleteConfirmCb(CallbackData, prefix="del_confirm"):
    confirmed: bool


def _delete_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Да, удалить",
                    callback_data=DeleteConfirmCb(confirmed=True).pack(),
                ),
                InlineKeyboardButton(
                    text="❌ Отмена",
                    callback_data=DeleteConfirmCb(confirmed=False).pack(),
                ),
            ]
        ]
    )


def _format_own_profile(data: dict) -> str:
    gender_icon = "♂️" if data.get("gender") == "male" else "♀️"
    interests = data.get("interests") or []
    interests_str = ", ".join(interests) if interests else "не указаны"
    bio = data.get("bio") or "не указано"
    photo_count = len(data.get("photos", []))
    photos_line = f"📸 Фото: {photo_count}" if photo_count else "📸 Фото: нет"
    return (
        f"<b>Ваша анкета</b>\n\n"
        f"<b>{data['name']}, {data['age']}</b> {gender_icon}\n"
        f"📍 {data['city']}\n"
        f"🎯 Интересы: {interests_str}\n"
        f"📝 {bio}\n"
        f"{photos_line}"
    )


# ─── /profile ─────────────────────────────────────────────────────────────────

@router.message(Command("profile"))
async def cmd_profile(message: Message):
    client = ProfileClient()
    try:
        profile = await client.get_profile(message.from_user.id)
    except Exception as exc:
        logger.error(f"profile: failed to fetch: {exc}")
        await message.answer("⚠️ Сервис временно недоступен. Попробуйте позже.")
        return

    if profile is None:
        await message.answer(
            "😔 У вас нет активной анкеты.\n"
            "Используйте /start чтобы создать её."
        )
        return

    text = _format_own_profile(profile)
    photos = profile.get("photos", [])

    if not photos:
        await message.answer(text, parse_mode="HTML")
        return

    media_client = MediaClient()

    if len(photos) == 1:
        photo = photos[0]
        if photo.get("object_key"):
            try:
                photo_bytes = await media_client.get_photo(photo["object_key"])
                await message.answer_photo(
                    photo=BufferedInputFile(photo_bytes, filename="photo.jpg"),
                    caption=text,
                    parse_mode="HTML",
                )
                return
            except Exception as exc:
                logger.warning(f"profile: could not load photo: {exc}")
        await message.answer(text, parse_mode="HTML")
        return

    # Multiple photos — send as media group; caption goes on the first item
    media_group: list[InputMediaPhoto] = []
    for idx, photo in enumerate(photos):
        if not photo.get("object_key"):
            continue
        try:
            photo_bytes = await media_client.get_photo(photo["object_key"])
            media_group.append(
                InputMediaPhoto(
                    media=BufferedInputFile(photo_bytes, filename=f"photo_{idx}.jpg"),
                    caption=text if idx == 0 else None,
                    parse_mode="HTML" if idx == 0 else None,
                )
            )
        except Exception as exc:
            logger.warning(f"profile: skipping photo {photo.get('id')}: {exc}")

    if media_group:
        await message.answer_media_group(media=media_group)
    else:
        await message.answer(text, parse_mode="HTML")


# ─── /delete ──────────────────────────────────────────────────────────────────

@router.message(Command("delete"))
async def cmd_delete(message: Message):
    await message.answer(
        "⚠️ Вы уверены, что хотите удалить анкету?\n"
        "Это действие скроет вас из поиска. "
        "Вы сможете создать новую анкету через /start.",
        reply_markup=_delete_keyboard(),
    )


@router.callback_query(DeleteConfirmCb.filter(F.confirmed == True))
async def cb_delete_confirmed(callback: CallbackQuery):
    client = ProfileClient()
    try:
        await client.delete_profile(callback.from_user.id)
    except Exception as exc:
        logger.error(f"delete: {exc}")
        await callback.message.edit_text("⚠️ Не удалось удалить анкету. Попробуйте позже.")
        await callback.answer()
        return

    await callback.message.edit_text(
        "✅ Анкета удалена.\n"
        "Чтобы создать новую, используйте /start."
    )
    await callback.answer()


@router.callback_query(DeleteConfirmCb.filter(F.confirmed == False))
async def cb_delete_cancelled(callback: CallbackQuery):
    await callback.message.edit_text("❌ Удаление отменено.")
    await callback.answer()
