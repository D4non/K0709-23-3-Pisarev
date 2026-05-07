from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
import redis.asyncio as aioredis

from app.models.database import get_session, get_redis
from app.models.orm import User
from app.schemas.user import ProfileResponse, PhotoOut
from app.crud.users import get_user_by_telegram_id
from app.services.cache import get_or_compute_next, invalidate
from shared.logger import setup_logger

logger = setup_logger("profile-service.api.recommendations")
router = APIRouter()


async def _fetch_user_by_id(session: AsyncSession, user_id: int) -> User | None:
    result = await session.execute(
        select(User)
        .where(User.id == user_id)
        .options(
            selectinload(User.profile),
            selectinload(User.interests),
            selectinload(User.photos),
        )
    )
    return result.scalar_one_or_none()


@router.get("/{telegram_id}", response_model=ProfileResponse)
async def get_recommendation(
    telegram_id: int,
    session: AsyncSession = Depends(get_session),
    redis: aioredis.Redis = Depends(get_redis),
):
    viewer = await get_user_by_telegram_id(session, telegram_id)
    if viewer is None or viewer.profile is None:
        raise HTTPException(
            status_code=404,
            detail="Viewer profile not found. Complete registration first.",
        )

    candidate_user_id = await get_or_compute_next(redis, session, telegram_id, viewer.id)
    if candidate_user_id is None:
        raise HTTPException(status_code=404, detail="No candidates available right now.")

    candidate = await _fetch_user_by_id(session, candidate_user_id)
    if candidate is None or candidate.profile is None:
        raise HTTPException(status_code=404, detail="Candidate profile not found.")

    logger.info(
        f"Returning candidate telegram_id={candidate.telegram_id} for viewer={telegram_id}"
    )
    return ProfileResponse(
        telegram_id=candidate.telegram_id,
        name=candidate.profile.name,
        age=candidate.profile.age,
        gender=candidate.profile.gender,
        city=candidate.profile.city,
        bio=candidate.profile.bio,
        interests=[i.interest for i in candidate.interests],
        photos=[
            PhotoOut(id=p.id, url=p.url, object_key=p.object_key, is_primary=p.is_primary)
            for p in candidate.photos
        ],
    )


@router.post("/{telegram_id}/refresh")
async def refresh_recommendations(
    telegram_id: int,
    redis: aioredis.Redis = Depends(get_redis),
):
    await invalidate(redis, telegram_id)
    return {"message": "Cache cleared. Next request will recompute recommendations."}
