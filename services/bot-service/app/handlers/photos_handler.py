import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from aiogram import Router, F
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

logger = setup_logger("bot-service.photos")
router = Router()


class PhotoActionCb(CallbackData, prefix="photo_mgr"):
    action: str       # "delete" | "primary"
    photo_id: int
    telegram_id: int


def _photo_keyboard(photo: dict, telegram_id: int) -> InlineKeyboardMarkup:
    buttons = [[
        InlineKeyboardButton(
            text="🗑 Удалить",
            callback_data=PhotoActionCb(
                action="delete", photo_id=photo["id"], telegram_id=telegram_id
            ).pack(),
        )
    ]]
    if not photo.get("is_primary"):
        buttons[0].append(
            InlineKeyboardButton(
                text="⭐ Сделать главным",
                callback_data=PhotoActionCb(
                    action="primary", photo_id=photo["id"], telegram_id=telegram_id
                ).pack(),
            )
        )
    return InlineKeyboardMarkup(inline_keyboard=buttons)


# ─── /photos ──────────────────────────────────────────────────────────────────

@router.message(Command("photos"))
async def cmd_photos(message: Message):
    client = ProfileClient()
    try:
        profile = await client.get_profile(message.from_user.id)
    except Exception as exc:
        logger.error(f"photos: failed to fetch profile: {exc}")
        await message.answer("⚠️ Сервис временно недоступен. Попробуйте позже.")
        return

    if profile is None:
        await message.answer(
            "😔 У вас нет активной анкеты.\n"
            "Используйте /start чтобы создать её."
        )
        return

    photos = profile.get("photos", [])
    if not photos:
        await message.answer(
            "📷 У вас пока нет фотографий.\n"
            "Добавьте их через /start (перерегистрация)."
        )
        return

    await message.answer(f"📷 Ваши фотографии ({len(photos)} шт.):")

    media_client = MediaClient()
    for photo in photos:
        label = "⭐ Главное фото" if photo.get("is_primary") else "Фото"
        caption = label
        keyboard = _photo_keyboard(photo, message.from_user.id)

        if photo.get("object_key"):
            try:
                photo_bytes = await media_client.get_photo(photo["object_key"])
                await message.answer_photo(
                    photo=BufferedInputFile(photo_bytes, filename="photo.jpg"),
                    caption=caption,
                    reply_markup=keyboard,
                )
                continue
            except Exception as exc:
                logger.warning(f"photos: could not load photo {photo['id']}: {exc}")

        await message.answer(
            text=f"{caption} (не удалось загрузить изображение)",
            reply_markup=keyboard,
        )


# ─── callbacks ────────────────────────────────────────────────────────────────

@router.callback_query(PhotoActionCb.filter(F.action == "delete"))
async def cb_photo_delete(callback: CallbackQuery, callback_data: PhotoActionCb):
    if callback_data.telegram_id != callback.from_user.id:
        await callback.answer("Недостаточно прав.", show_alert=True)
        return

    client = ProfileClient()
    try:
        await client.delete_photo(callback_data.telegram_id, callback_data.photo_id)
    except Exception as exc:
        logger.error(f"photo delete: {exc}")
        await callback.answer("⚠️ Не удалось удалить фото.", show_alert=True)
        return

    try:
        await callback.message.delete()
    except Exception:
        await callback.message.edit_caption("🗑 Фото удалено.")

    await callback.answer("Фото удалено.")


@router.callback_query(PhotoActionCb.filter(F.action == "primary"))
async def cb_photo_primary(callback: CallbackQuery, callback_data: PhotoActionCb):
    if callback_data.telegram_id != callback.from_user.id:
        await callback.answer("Недостаточно прав.", show_alert=True)
        return

    client = ProfileClient()
    try:
        await client.set_primary_photo(callback_data.telegram_id, callback_data.photo_id)
    except Exception as exc:
        logger.error(f"photo primary: {exc}")
        await callback.answer("⚠️ Не удалось обновить главное фото.", show_alert=True)
        return

    # Update caption and remove the "Сделать главным" button
    try:
        await callback.message.edit_caption(
            caption="⭐ Главное фото",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(
                    text="🗑 Удалить",
                    callback_data=PhotoActionCb(
                        action="delete",
                        photo_id=callback_data.photo_id,
                        telegram_id=callback_data.telegram_id,
                    ).pack(),
                )
            ]]),
        )
    except Exception:
        pass

    await callback.answer("⭐ Теперь это главное фото.")
