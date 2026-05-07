from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.database import get_session
from app.schemas.user import MatchedProfile
from app.crud.users import get_user_by_telegram_id
from app.crud.interactions import get_matches_for_user
from shared.logger import setup_logger

logger = setup_logger("profile-service.api.matches")
router = APIRouter()


@router.get("/{telegram_id}", response_model=list[MatchedProfile])
async def get_matches(
    telegram_id: int,
    session: AsyncSession = Depends(get_session),
):
    user = await get_user_by_telegram_id(session, telegram_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    partners = await get_matches_for_user(session, user.id)
    result = []
    for partner in partners:
        if not partner.profile or not partner.profile.is_active:
            continue
        primary = next(
            (p for p in partner.photos if p.is_primary),
            partner.photos[0] if partner.photos else None,
        )
        result.append(
            MatchedProfile(
                telegram_id=partner.telegram_id,
                name=partner.profile.name,
                age=partner.profile.age,
                city=partner.profile.city,
                primary_photo_object_key=primary.object_key if primary else None,
            )
        )
    return result
