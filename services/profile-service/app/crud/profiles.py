from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.models.orm import User, UserProfile


async def get_active_candidates(session: AsyncSession, exclude_user_id: int, already_seen_ids: set[int]) -> list[User]:
    """Return all active users with profiles, excluding the viewer and already-seen candidates."""
    exclude_ids = already_seen_ids | {exclude_user_id}

    result = await session.execute(
        select(User)
        .join(UserProfile, User.id == UserProfile.user_id)
        .where(UserProfile.is_active.is_(True))
        .where(~User.id.in_(exclude_ids))
        .options(
            selectinload(User.profile),
            selectinload(User.interests),
            selectinload(User.preferences),
            selectinload(User.photos),
            selectinload(User.received_interactions),
        )
    )
    return list(result.scalars().all())


async def deactivate_profile(session: AsyncSession, user_id: int) -> None:
    result = await session.execute(
        select(UserProfile).where(UserProfile.user_id == user_id)
    )
    profile = result.scalar_one_or_none()
    if profile:
        profile.is_active = False
        await session.commit()
