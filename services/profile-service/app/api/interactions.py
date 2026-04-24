from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.database import get_session, get_redis
from app.schemas.interaction import InteractionRequest, InteractionResponse
from app.crud.users import get_user_by_telegram_id
from app.crud.interactions import record_like, record_skip
from app.services.cache import invalidate
from shared.logger import setup_logger

import redis.asyncio as aioredis

logger = setup_logger("profile-service.api.interactions")
router = APIRouter()


@router.post("", response_model=InteractionResponse)
async def post_interaction(
    body: InteractionRequest,
    session: AsyncSession = Depends(get_session),
    redis: aioredis.Redis = Depends(get_redis),
):
    viewer = await get_user_by_telegram_id(session, body.viewer_telegram_id)
    candidate = await get_user_by_telegram_id(session, body.candidate_telegram_id)

    if viewer is None:
        raise HTTPException(status_code=404, detail="Viewer not found")
    if candidate is None:
        raise HTTPException(status_code=404, detail="Candidate not found")

    is_match = False
    candidate_name = candidate.profile.name if candidate.profile else None
    viewer_name = viewer.profile.name if viewer.profile else None

    if body.action == "like":
        _, is_match = await record_like(session, viewer.id, candidate.id)
        if is_match:
            # Invalidate both parties' caches so they see each other differently
            await invalidate(redis, body.viewer_telegram_id)
            await invalidate(redis, body.candidate_telegram_id)
            logger.info(
                f"Match! telegram_ids={body.viewer_telegram_id} <-> {body.candidate_telegram_id}"
            )
    else:
        await record_skip(session, viewer.id, candidate.id)

    return InteractionResponse(
        success=True,
        is_match=is_match,
        candidate_name=candidate_name if is_match else None,
        viewer_name=viewer_name if is_match else None,
    )
