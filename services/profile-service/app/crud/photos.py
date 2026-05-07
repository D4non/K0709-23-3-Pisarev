from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update

from app.models.orm import UserPhoto


async def add_photo(
    session: AsyncSession,
    user_id: int,
    object_key: str,
    url: str,
    is_primary: bool = False,
) -> UserPhoto:
    if is_primary:
        await session.execute(
            update(UserPhoto)
            .where(UserPhoto.user_id == user_id)
            .values(is_primary=False)
        )
    photo = UserPhoto(user_id=user_id, object_key=object_key, url=url, is_primary=is_primary)
    session.add(photo)
    await session.commit()
    await session.refresh(photo)
    return photo


async def get_photo_by_id(
    session: AsyncSession, photo_id: int, user_id: int
) -> UserPhoto | None:
    result = await session.execute(
        select(UserPhoto).where(
            UserPhoto.id == photo_id,
            UserPhoto.user_id == user_id,
        )
    )
    return result.scalar_one_or_none()


async def delete_photo_record(session: AsyncSession, photo: UserPhoto) -> None:
    await session.delete(photo)
    await session.commit()


async def set_primary_photo(
    session: AsyncSession, photo_id: int, user_id: int
) -> UserPhoto | None:
    await session.execute(
        update(UserPhoto)
        .where(UserPhoto.user_id == user_id)
        .values(is_primary=False)
    )
    result = await session.execute(
        select(UserPhoto).where(
            UserPhoto.id == photo_id,
            UserPhoto.user_id == user_id,
        )
    )
    photo = result.scalar_one_or_none()
    if photo:
        photo.is_primary = True
        await session.commit()
    return photo
