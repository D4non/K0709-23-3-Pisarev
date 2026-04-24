from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.models.orm import User, UserProfile, UserInterest, UserPreferences


async def get_user_by_telegram_id(session: AsyncSession, telegram_id: int) -> User | None:
    result = await session.execute(
        select(User)
        .where(User.telegram_id == telegram_id)
        .options(
            selectinload(User.profile),
            selectinload(User.interests),
            selectinload(User.preferences),
            selectinload(User.photos),
        )
    )
    return result.scalar_one_or_none()


async def get_user_by_id(session: AsyncSession, user_id: int) -> User | None:
    result = await session.execute(
        select(User)
        .where(User.id == user_id)
        .options(
            selectinload(User.profile),
            selectinload(User.interests),
            selectinload(User.preferences),
            selectinload(User.photos),
        )
    )
    return result.scalar_one_or_none()


async def create_or_update_user(
    session: AsyncSession,
    telegram_id: int,
    username: str | None,
    name: str,
    age: int,
    gender: str,
    city: str,
    bio: str | None,
    interests: list[str],
    min_age: int = 18,
    max_age: int = 99,
    preferred_gender: str | None = None,
) -> User:
    user = await get_user_by_telegram_id(session, telegram_id)

    if user is None:
        user = User(telegram_id=telegram_id, username=username)
        session.add(user)
        await session.flush()
        result = await session.execute(
            select(User)
            .where(User.id == user.id)
            .options(
                selectinload(User.profile),
                selectinload(User.interests),
                selectinload(User.preferences),
                selectinload(User.photos),
            )
        )
        user = result.scalar_one()
    else:
        user.username = username

    # Upsert profile
    if user.profile is None:
        profile = UserProfile(user_id=user.id, name=name, age=age, gender=gender, city=city, bio=bio or None)
        session.add(profile)
    else:
        user.profile.name = name
        user.profile.age = age
        user.profile.gender = gender
        user.profile.city = city
        user.profile.bio = bio or None

    # Replace interests
    for old in list(user.interests):
        await session.delete(old)
    await session.flush()
    for interest in interests:
        if interest:
            session.add(UserInterest(user_id=user.id, interest=interest.lower().strip()))

    # Upsert preferences
    if user.preferences is None:
        prefs = UserPreferences(
            user_id=user.id,
            min_age=min_age,
            max_age=max_age,
            preferred_gender=preferred_gender,
        )
        session.add(prefs)
    else:
        user.preferences.min_age = min_age
        user.preferences.max_age = max_age
        user.preferences.preferred_gender = preferred_gender

    await session.commit()
    await session.refresh(user)
    return user
