from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.orm import CandidateBehavioralStats


async def _get_or_create_stats(
    session: AsyncSession, viewer_id: int, candidate_id: int
) -> CandidateBehavioralStats:
    result = await session.execute(
        select(CandidateBehavioralStats).where(
            CandidateBehavioralStats.viewer_id == viewer_id,
            CandidateBehavioralStats.candidate_id == candidate_id,
        )
    )
    stats = result.scalar_one_or_none()
    if stats is None:
        stats = CandidateBehavioralStats(viewer_id=viewer_id, candidate_id=candidate_id)
        session.add(stats)
        await session.flush()
    return stats


async def record_like(
    session: AsyncSession, viewer_id: int, candidate_id: int
) -> tuple[CandidateBehavioralStats, bool]:
    """Record a like. Returns (stats, is_mutual_match)."""
    stats = await _get_or_create_stats(session, viewer_id, candidate_id)
    stats.likes_given += 1
    stats.updated_at = datetime.utcnow()

    # Check if candidate has previously liked the viewer
    reverse_result = await session.execute(
        select(CandidateBehavioralStats).where(
            CandidateBehavioralStats.viewer_id == candidate_id,
            CandidateBehavioralStats.candidate_id == viewer_id,
        )
    )
    reverse_stats = reverse_result.scalar_one_or_none()
    is_match = reverse_stats is not None and reverse_stats.likes_given > 0

    if is_match:
        stats.is_matched = True
        if reverse_stats:
            reverse_stats.is_matched = True

    await session.commit()
    return stats, is_match


async def record_skip(
    session: AsyncSession, viewer_id: int, candidate_id: int
) -> CandidateBehavioralStats:
    stats = await _get_or_create_stats(session, viewer_id, candidate_id)
    stats.skips_given += 1
    stats.updated_at = datetime.utcnow()
    await session.commit()
    return stats


async def get_seen_candidate_ids(session: AsyncSession, viewer_id: int) -> set[int]:
    """Return IDs of all users the viewer has already interacted with."""
    result = await session.execute(
        select(CandidateBehavioralStats.candidate_id).where(
            CandidateBehavioralStats.viewer_id == viewer_id
        )
    )
    return set(result.scalars().all())
