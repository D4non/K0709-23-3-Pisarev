from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.database import get_session
from app.schemas.user import StatsResponse
from app.crud.users import get_user_by_telegram_id
from app.crud.stats import get_user_stats
from shared.logger import setup_logger

logger = setup_logger("profile-service.api.stats")
router = APIRouter()


@router.get("/{telegram_id}", response_model=StatsResponse)
async def get_stats(
    telegram_id: int,
    session: AsyncSession = Depends(get_session),
):
    user = await get_user_by_telegram_id(session, telegram_id)
    if user is None or user.profile is None:
        raise HTTPException(status_code=404, detail="Profile not found")

    stats = await get_user_stats(session, user.id)

    return StatsResponse(
        likes_received=stats["likes_received"],
        skips_received=stats["skips_received"],
        likes_given=stats["likes_given"],
        matches=stats["matches"],
        photos_count=len(user.photos),
        registered_at=user.created_at.strftime("%d.%m.%Y"),
    )
