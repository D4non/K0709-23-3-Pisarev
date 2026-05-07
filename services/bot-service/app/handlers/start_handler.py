"""
/start command handler — user registration with photo upload.

Flow:
  name → age → gender → city → bio → interests
  → register user in profile-service
  → waiting_for_photos (upload 1..N photos, /done or /skip to finish)
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.filters import Command, StateFilter

from app.services.states import RegistrationState
from app.services.profile_client import ProfileClient
from app.services.media_client import MediaClient
from shared.logger import setup_logger

logger = setup_logger("start_handler")
router = Router()


# ─── /start ───────────────────────────────────────────────────────────────────

@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        f"👋 Привет, {message.from_user.first_name}!\n\n"
        "Добро пожаловать в Dating Bot!\n"
        "Давайте заполним вашу анкету.\n\n"
        "Как вас зовут?"
    )
    await state.set_state(RegistrationState.waiting_for_name)


# ─── registration steps ────────────────────────────────────────────────────────

@router.message(RegistrationState.waiting_for_name)
async def process_name(message: Message, state: FSMContext):
    name = message.text.strip()
    if len(name) < 2 or len(name) > 50:
        await message.answer("❌ Имя должно быть от 2 до 50 символов. Попробуйте снова:")
        return

    await state.update_data(name=name)
    await message.answer(
        f"Приятно познакомиться, {name}! 😊\n\n"
        "Сколько вам лет? (от 18 до 99):"
    )
    await state.set_state(RegistrationState.waiting_for_age)


@router.message(RegistrationState.waiting_for_age)
async def process_age(message: Message, state: FSMContext):
    try:
        age = int(message.text.strip())
        if age < 18 or age > 99:
            raise ValueError
    except ValueError:
        await message.answer("❌ Введите возраст числом от 18 до 99:")
        return

    await state.update_data(age=age)

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="👨 Мужской", callback_data="gender_male"),
            InlineKeyboardButton(text="👩 Женский", callback_data="gender_female"),
        ],
    ])
    await message.answer("Выберите ваш пол:", reply_markup=keyboard)
    await state.set_state(RegistrationState.waiting_for_gender)


@router.callback_query(StateFilter(RegistrationState.waiting_for_gender))
async def process_gender(callback: CallbackQuery, state: FSMContext):
    gender_map = {"gender_male": "male", "gender_female": "female"}
    gender = gender_map.get(callback.data)
    await state.update_data(gender=gender)
    await callback.message.answer("Из какого вы города? 🏙️")
    await state.set_state(RegistrationState.waiting_for_city)
    await callback.answer()


@router.message(RegistrationState.waiting_for_city)
async def process_city(message: Message, state: FSMContext):
    city = message.text.strip()
    if len(city) < 2:
        await message.answer("❌ Пожалуйста, введите название города:")
        return

    await state.update_data(city=city)
    await message.answer(
        "Расскажите немного о себе (необязательно):\n"
        "(отправьте /skip для пропуска)"
    )
    await state.set_state(RegistrationState.waiting_for_bio)


@router.message(Command("skip"), RegistrationState.waiting_for_bio)
@router.message(RegistrationState.waiting_for_bio)
async def process_bio(message: Message, state: FSMContext):
    bio = message.text.strip() if not message.text.startswith("/skip") else ""
    await state.update_data(bio=bio)

    await message.answer(
        "Какие у вас интересы? (через запятую)\n"
        "Например: музыка, спорт, кино\n"
        "(отправьте /skip для пропуска)"
    )
    await state.set_state(RegistrationState.waiting_for_interests)


@router.message(Command("skip"), RegistrationState.waiting_for_interests)
@router.message(RegistrationState.waiting_for_interests)
async def process_interests(message: Message, state: FSMContext):
    if not message.text.startswith("/skip"):
        interests = [i.strip() for i in message.text.split(",") if i.strip()]
    else:
        interests = []

    await state.update_data(interests=interests, photo_count=0)

    # Register user so photos can be attached to the profile
    data = await state.get_data()
    client = ProfileClient()
    try:
        await client.register(
            telegram_id=message.from_user.id,
            username=message.from_user.username,
            name=data["name"],
            age=data["age"],
            gender=data["gender"],
            city=data["city"],
            bio=data.get("bio") or None,
            interests=interests,
        )
        logger.info(f"User registered: telegram_id={message.from_user.id}")
    except Exception as exc:
        logger.error(f"Failed to register user: {exc}")
        await message.answer("⚠️ Регистрация временно недоступна. Попробуйте /start позже.")
        await state.clear()
        return

    await message.answer(
        "📸 Отлично! Теперь добавьте фотографии для анкеты.\n\n"
        "Отправляйте фото по одному — первое станет главным.\n"
        "Когда закончите, напишите /done\n"
        "Чтобы пропустить фото — /skip"
    )
    await state.set_state(RegistrationState.waiting_for_photos)


# ─── photo upload ──────────────────────────────────────────────────────────────

@router.message(F.photo, RegistrationState.waiting_for_photos)
async def process_photo(message: Message, state: FSMContext):
    state_data = await state.get_data()
    photo_count = state_data.get("photo_count", 0)

    # Download from Telegram (use highest resolution)
    tg_photo = message.photo[-1]
    try:
        file_info = await message.bot.get_file(tg_photo.file_id)
        downloaded = await message.bot.download_file(file_info.file_path)
        photo_bytes = downloaded.read()
    except Exception as exc:
        logger.error(f"Failed to download photo from Telegram: {exc}")
        await message.answer("⚠️ Не удалось получить фото от Telegram. Попробуйте ещё раз.")
        return

    # Upload to media-service → MinIO
    media = MediaClient()
    try:
        upload_result = await media.upload_photo(
            telegram_id=message.from_user.id,
            photo_bytes=photo_bytes,
            filename=f"{tg_photo.file_id}.jpg",
        )
    except Exception as exc:
        logger.error(f"Failed to upload photo to media-service: {exc}")
        await message.answer("⚠️ Ошибка загрузки фото. Попробуйте ещё раз.")
        return

    # Save URL + object_key to profile-service
    profile = ProfileClient()
    try:
        await profile.add_photo(
            telegram_id=message.from_user.id,
            object_key=upload_result["object_key"],
            url=upload_result["url"],
            is_primary=(photo_count == 0),
        )
    except Exception as exc:
        logger.error(f"Failed to save photo record to profile-service: {exc}")
        await message.answer("⚠️ Ошибка сохранения фото. Попробуйте ещё раз.")
        return

    photo_count += 1
    await state.update_data(photo_count=photo_count)
    await message.answer(
        f"✅ Фото #{photo_count} добавлено!\n"
        "Отправьте ещё или напишите /done"
    )


@router.message(Command("done"), RegistrationState.waiting_for_photos)
@router.message(Command("skip"), RegistrationState.waiting_for_photos)
async def finish_registration(message: Message, state: FSMContext):
    data = await state.get_data()
    await state.clear()

    photo_count = data.get("photo_count", 0)
    interests = data.get("interests", [])
    gender_icon = "♂️" if data["gender"] == "male" else "♀️"

    await message.answer(
        "🎉 Регистрация завершена!\n\n"
        f"📋 <b>Ваша анкета:</b>\n"
        f"👤 {data['name']}\n"
        f"{gender_icon} Пол: {'Мужской' if data['gender'] == 'male' else 'Женский'}\n"
        f"🎂 Возраст: {data['age']}\n"
        f"🏙️ Город: {data['city']}\n"
        f"💬 О себе: {data.get('bio') or 'не указано'}\n"
        f"🎯 Интересы: {', '.join(interests) or 'не указаны'}\n"
        f"📸 Фотографий: {photo_count}\n\n"
        "Используйте /browse чтобы смотреть анкеты других пользователей.\n\n"
        "<b>Доступные команды:</b>\n"
        "/profile — посмотреть свою анкету\n"
        "/photos — управлять фотографиями анкеты\n"
        "/stats — посмотреть статистику\n"
        "/delete — удалить анкету"
    )
