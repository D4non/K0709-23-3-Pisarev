from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import func, select

from app.models.orm import CandidateBehavioralStats


async def get_user_stats(session: AsyncSession, user_id: int) -> dict:
    likes_received = await session.scalar(
        select(func.count()).where(
            CandidateBehavioralStats.candidate_id == user_id,
            CandidateBehavioralStats.likes_given > 0,
        )
    ) or 0

    skips_received = await session.scalar(
        select(func.count()).where(
            CandidateBehavioralStats.candidate_id == user_id,
            CandidateBehavioralStats.skips_given > 0,
        )
    ) or 0

    likes_given = await session.scalar(
        select(func.sum(CandidateBehavioralStats.likes_given)).where(
            CandidateBehavioralStats.viewer_id == user_id,
        )
    ) or 0

    matches = await session.scalar(
        select(func.count()).where(
            CandidateBehavioralStats.viewer_id == user_id,
            CandidateBehavioralStats.is_matched == True,
        )
    ) or 0

    return {
        "likes_received": int(likes_received),
        "skips_received": int(skips_received),
        "likes_given": int(likes_given),
        "matches": int(matches),
    }
