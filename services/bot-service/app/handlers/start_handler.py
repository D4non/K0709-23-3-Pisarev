"""
/start command handler — user registration.
Collects user data and stores telegram_id as the primary identifier.
"""
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.filters import Command, StateFilter

from app.services.states import RegistrationState
from shared.config import settings
from shared.logger import setup_logger

logger = setup_logger("start_handler")

router = Router()


@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    """Handle /start — begin registration."""
    telegram_id = message.from_user.id
    logger.info(f"User /start: telegram_id={telegram_id}")

    await message.answer(
        f"👋 Привет, {message.from_user.first_name}!\n\n"
        "Добро пожаловать в Dating Bot!\n"
        "Давайте заполним вашу анкету.\n\n"
        "Как вас зовут?"
    )
    await state.set_state(RegistrationState.waiting_for_name)


@router.message(RegistrationState.waiting_for_name)
async def process_name(message: Message, state: FSMContext):
    """Process name input."""
    name = message.text.strip()
    if len(name) < 2 or len(name) > 50:
        await message.answer("❌ Имя должно быть от 2 до 50 символов. Попробуйте снова:")
        return

    await state.update_data(name=name)
    await message.answer(
        f"Приятно познакомиться, {name}! 😊\n\n"
        "Сколько вам лет? (введите число от 18 до 99):"
    )
    await state.set_state(RegistrationState.waiting_for_age)


@router.message(RegistrationState.waiting_for_age)
async def process_age(message: Message, state: FSMContext):
    """Process age input."""
    try:
        age = int(message.text.strip())
        if age < 18 or age > 99:
            await message.answer("❌ Возраст должен быть от 18 до 99. Попробуйте снова:")
            return
    except ValueError:
        await message.answer("❌ Пожалуйста, введите число:")
        return

    await state.update_data(age=age)

    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

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
    """Process gender selection."""
    gender_map = {
        "gender_male": "male",
        "gender_female": "female",
    }
    gender = gender_map.get(callback.data)
    await state.update_data(gender=gender)
    await callback.message.answer("Из какого вы города? 🏙️")
    await state.set_state(RegistrationState.waiting_for_city)
    await callback.answer()


@router.message(RegistrationState.waiting_for_city)
async def process_city(message: Message, state: FSMContext):
    """Process city input."""
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
    """Process bio input."""
    if message.text and not message.text.startswith("/skip"):
        await state.update_data(bio=message.text.strip())
    else:
        await state.update_data(bio="")

    await message.answer(
        "Какие у вас интересы? (через запятую)\n"
        "Например: музыка, спорт, кино\n"
        "(отправьте /skip для пропуска)"
    )
    await state.set_state(RegistrationState.waiting_for_interests)


@router.message(Command("skip"), RegistrationState.waiting_for_interests)
@router.message(RegistrationState.waiting_for_interests)
async def process_interests(message: Message, state: FSMContext):
    """Process interests and complete registration."""
    if message.text and not message.text.startswith("/skip"):
        interests = [i.strip() for i in message.text.split(",") if i.strip()]
    else:
        interests = []

    data = await state.get_data()
    telegram_id = message.from_user.id

    # --- Registration complete ---
    # telegram_id stored as primary identifier.
    # In Stage 3 this data will be sent to profile-service / database.

    logger.info(
        f"Registration complete: telegram_id={telegram_id}, "
        f"name={data.get('name')}, age={data.get('age')}, "
        f"gender={data.get('gender')}, city={data.get('city')}, "
        f"interests={interests}"
    )

    await message.answer(
        "🎉 Регистрация завершена!\n\n"
        f"📋 <b>Ваша анкета:</b>\n"
        f"👤 Имя: {data.get('name')}\n"
        f"🎂 Возраст: {data.get('age')}\n"
        f"{'♂️' if data.get('gender') == 'male' else '♀️'} Пол: {data.get('gender')}\n"
        f"🏙️ Город: {data.get('city')}\n"
        f"💬 О себе: {data.get('bio', 'Не указано') or 'Не указано'}\n"
        f"🎯 Интересы: {', '.join(interests) or 'Не указаны'}\n\n"
        f"🆔 Telegram ID: <code>{telegram_id}</code>\n\n"
        "Функции просмотра анкет и взаимодействия будут добавлены на следующих этапах."
    )

    await state.clear()
