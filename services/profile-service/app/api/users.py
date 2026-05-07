from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.database import get_session, get_redis
from app.schemas.user import RegisterUserRequest, RegisterUserResponse, ProfileResponse, PhotoOut
from app.crud.users import create_or_update_user, get_user_by_telegram_id
from app.services.cache import invalidate
import redis.asyncio as aioredis
from shared.logger import setup_logger

logger = setup_logger("profile-service.api.users")
router = APIRouter()


@router.post("/register", response_model=RegisterUserResponse)
async def register_user(
    body: RegisterUserRequest,
    session: AsyncSession = Depends(get_session),
):
    user = await create_or_update_user(
        session=session,
        telegram_id=body.telegram_id,
        username=body.username,
        name=body.name,
        age=body.age,
        gender=body.gender,
        city=body.city,
        bio=body.bio,
        interests=body.interests,
        min_age=body.min_age,
        max_age=body.max_age,
        preferred_gender=body.preferred_gender,
    )
    logger.info(f"User registered/updated: telegram_id={body.telegram_id}, user_id={user.id}")
    return RegisterUserResponse(
        user_id=user.id,
        telegram_id=user.telegram_id,
        message="ok",
    )


@router.get("/{telegram_id}", response_model=ProfileResponse)
async def get_profile(
    telegram_id: int,
    session: AsyncSession = Depends(get_session),
):
    user = await get_user_by_telegram_id(session, telegram_id)
    if user is None or user.profile is None:
        raise HTTPException(status_code=404, detail="Profile not found")

    return ProfileResponse(
        telegram_id=user.telegram_id,
        name=user.profile.name,
        age=user.profile.age,
        gender=user.profile.gender,
        city=user.profile.city,
        bio=user.profile.bio,
        interests=[i.interest for i in user.interests],
        photos=[
            PhotoOut(id=p.id, url=p.url, object_key=p.object_key, is_primary=p.is_primary)
            for p in user.photos
        ],
    )


@router.delete("/{telegram_id}")
async def delete_profile(
    telegram_id: int,
    session: AsyncSession = Depends(get_session),
    redis: aioredis.Redis = Depends(get_redis),
):
    user = await get_user_by_telegram_id(session, telegram_id)
    if user is None or user.profile is None:
        raise HTTPException(status_code=404, detail="Profile not found")

    user.profile.is_active = False
    await session.commit()
    await invalidate(redis, telegram_id)

    logger.info(f"Profile deactivated: telegram_id={telegram_id}")
    return {"message": "Profile deactivated. Use /start to create a new one."}
