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
from aiogram.fsm.context import FSMContext

from app.services.profile_client import ProfileClient
from app.services.media_client import MediaClient
from app.services.states import ChatState
from shared.logger import setup_logger

logger = setup_logger("bot-service.chat")
router = Router()


class ChatSelectCb(CallbackData, prefix="chat_sel"):
    partner_id: int


def _matches_keyboard(matches: list[dict]) -> InlineKeyboardMarkup:
    buttons = [
        [
            InlineKeyboardButton(
                text=f"💬 {m['name']}, {m['age']} — {m['city']}",
                callback_data=ChatSelectCb(partner_id=m["telegram_id"]).pack(),
            )
        ]
        for m in matches
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


# ─── /chats ───────────────────────────────────────────────────────────────────

@router.message(Command("chats"))
async def cmd_chats(message: Message, state: FSMContext):
    current = await state.get_state()
    if current == ChatState.chatting:
        data = await state.get_data()
        await message.answer(
            f"Вы уже в чате с <b>{data.get('partner_name', '...')}</b>.\n"
            "Напишите /stopchat чтобы выйти.",
            parse_mode="HTML",
        )
        return

    client = ProfileClient()
    try:
        matches = await client.get_matches(message.from_user.id)
    except Exception as exc:
        logger.error(f"chats: failed to fetch matches: {exc}")
        await message.answer("⚠️ Сервис временно недоступен. Попробуйте позже.")
        return

    if not matches:
        await message.answer(
            "😔 У вас пока нет взаимных симпатий.\n"
            "Используйте /browse чтобы найти кого-то!"
        )
        return

    await message.answer(
        f"💕 Ваши совпадения ({len(matches)}).\nВыберите, с кем хотите поговорить:",
        reply_markup=_matches_keyboard(matches),
    )


@router.callback_query(ChatSelectCb.filter())
async def cb_chat_select(
    callback: CallbackQuery,
    callback_data: ChatSelectCb,
    state: FSMContext,
):
    client = ProfileClient()
    try:
        partner_profile = await client.get_profile(callback_data.partner_id)
    except Exception as exc:
        logger.error(f"chat select: failed to fetch partner profile: {exc}")
        await callback.answer("⚠️ Не удалось открыть чат. Попробуйте позже.", show_alert=True)
        return

    if partner_profile is None:
        await callback.answer("😔 Анкета пользователя больше не активна.", show_alert=True)
        return

    partner_name = partner_profile["name"]

    # Fetch own name to include in relayed messages
    try:
        own_profile = await client.get_profile(callback.from_user.id)
        my_name = own_profile["name"] if own_profile else (callback.from_user.first_name or "Аноним")
    except Exception:
        my_name = callback.from_user.first_name or "Аноним"

    await state.set_state(ChatState.chatting)
    await state.update_data(
        partner_id=callback_data.partner_id,
        partner_name=partner_name,
        my_name=my_name,
    )

    await callback.message.edit_text(
        f"💬 Чат с <b>{partner_name}</b> открыт.\n"
        "Пишите сообщения — они будут переданы собеседнику.\n"
        "Отправьте /stopchat чтобы завершить чат.",
        parse_mode="HTML",
    )
    await callback.answer()


# ─── /stopchat ────────────────────────────────────────────────────────────────

@router.message(ChatState.chatting, Command("stopchat"))
async def cmd_stopchat(message: Message, state: FSMContext):
    data = await state.get_data()
    partner_name = data.get("partner_name", "собеседником")
    await state.clear()
    await message.answer(
        f"✅ Чат с <b>{partner_name}</b> завершён.\n"
        "Вы можете открыть его снова через /chats.",
        parse_mode="HTML",
    )


# ─── message relay ────────────────────────────────────────────────────────────

async def _relay_header(bot: Bot, chat_id: int, sender_name: str) -> None:
    await bot.send_message(chat_id, f"💬 <b>{sender_name}</b>:", parse_mode="HTML")


@router.message(ChatState.chatting, F.text)
async def relay_text(message: Message, state: FSMContext):
    data = await state.get_data()
    partner_id: int = data["partner_id"]
    my_name: str = data["my_name"]

    try:
        await message.bot.send_message(
            chat_id=partner_id,
            text=f"💬 <b>{my_name}</b>:\n{message.text}",
            parse_mode="HTML",
        )
        await message.answer("✓", parse_mode=None)
    except Exception as exc:
        logger.error(f"relay text to {partner_id}: {exc}")
        await message.answer("⚠️ Не удалось доставить сообщение.")


@router.message(ChatState.chatting, F.photo)
async def relay_photo(message: Message, state: FSMContext):
    data = await state.get_data()
    partner_id: int = data["partner_id"]
    my_name: str = data["my_name"]

    caption_prefix = f"💬 <b>{my_name}</b>:"
    original_caption = message.caption or ""
    full_caption = f"{caption_prefix}\n{original_caption}" if original_caption else caption_prefix

    try:
        # Forward the highest-quality photo
        file_id = message.photo[-1].file_id
        await message.bot.send_photo(
            chat_id=partner_id,
            photo=file_id,
            caption=full_caption,
            parse_mode="HTML",
        )
        await message.answer("✓", parse_mode=None)
    except Exception as exc:
        logger.error(f"relay photo to {partner_id}: {exc}")
        await message.answer("⚠️ Не удалось доставить фото.")


@router.message(ChatState.chatting, F.sticker | F.voice | F.video | F.video_note | F.audio | F.document)
async def relay_media(message: Message, state: FSMContext):
    data = await state.get_data()
    partner_id: int = data["partner_id"]
    my_name: str = data["my_name"]

    try:
        await _relay_header(message.bot, partner_id, my_name)
        await message.copy_to(chat_id=partner_id)
        await message.answer("✓", parse_mode=None)
    except Exception as exc:
        logger.error(f"relay media to {partner_id}: {exc}")
        await message.answer("⚠️ Не удалось доставить сообщение.")


@router.message(ChatState.chatting)
async def relay_unsupported(message: Message, state: FSMContext):
    await message.answer("⚠️ Этот тип сообщения не поддерживается в чате.")
