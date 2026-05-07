"""
Celery tasks for periodic rating recomputation (rating-aggregator component).

Task 1 — recompute_behavioral_scores (every 30 min):
    Reads all candidate_behavioral_stats rows, calculates Level 2 score for
    each candidate, and logs aggregated results. Stats themselves are already
    updated in real time by the interactions API; this task acts as a
    consistency check and produces monitoring-ready metrics.

Task 2 — recompute_combined_snapshots (every hour):
    For every active viewer-candidate pair (not yet seen by the viewer),
    computes Level 1 + Level 2 + Level 3 scores and upserts the result into
    user_candidate_ratings_snapshot. The recommendation service reads these
    pre-computed rows instead of recalculating on every API request.

Both tasks use asyncio.run() to drive the existing async SQLAlchemy setup
from a synchronous Celery worker context.
"""
import asyncio
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.celery_app import celery_app
from app.models.database import AsyncSessionLocal
from app.models.orm import (
    User,
    UserProfile,
    CandidateBehavioralStats,
    UserCandidateRatingSnapshot,
)
from app.services.rating import calculate_level1, calculate_level2, calculate_combined
from app.crud.interactions import get_seen_candidate_ids
from app.crud.profiles import get_active_candidates
from shared.logger import setup_logger

logger = setup_logger("rating-aggregator")


# ─── async helpers ────────────────────────────────────────────────────────────

async def _recompute_behavioral_async() -> dict:
    """
    Level 2 recomputation: calculate behavioral_score for every candidate
    that has at least one interaction row, then return a summary dict.
    No DB writes needed here — behavioral scores are derived on-the-fly from
    the raw candidate_behavioral_stats counters that the interactions API
    already keeps up to date.
    """
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(CandidateBehavioralStats.candidate_id).distinct()
        )
        candidate_ids = list(result.scalars().all())

        scores: dict[int, float] = {}
        for cid in candidate_ids:
            stats_result = await session.execute(
                select(CandidateBehavioralStats).where(
                    CandidateBehavioralStats.candidate_id == cid
                )
            )
            stats = stats_result.scalars().all()
            scores[cid] = calculate_level2(stats)

        # Log distribution for monitoring
        if scores:
            avg = sum(scores.values()) / len(scores)
            logger.info(
                f"[behavioral] candidates={len(scores)} avg_score={avg:.3f}",
            )

        return {
            "candidates_processed": len(scores),
            "computed_at": datetime.utcnow().isoformat(),
        }


async def _recompute_snapshots_async() -> dict:
    """
    Level 3 recomputation: for every active viewer, compute combined score
    against every unseen candidate and upsert into user_candidate_ratings_snapshot.
    """
    async with AsyncSessionLocal() as session:
        viewers_result = await session.execute(
            select(User)
            .join(UserProfile, User.id == UserProfile.user_id)
            .where(UserProfile.is_active.is_(True))
            .options(
                selectinload(User.profile),
                selectinload(User.interests),
                selectinload(User.preferences),
            )
        )
        viewers = list(viewers_result.scalars().all())

        total_snapshots = 0

        for viewer in viewers:
            seen_ids = await get_seen_candidate_ids(session, viewer.id)
            candidates = await get_active_candidates(session, viewer.id, seen_ids)

            for candidate in candidates:
                if candidate.profile is None:
                    continue

                l1 = calculate_level1(viewer, candidate)
                l2 = calculate_level2(candidate.received_interactions)
                interaction_count = sum(
                    s.likes_given + s.skips_given
                    for s in candidate.received_interactions
                )
                combined = calculate_combined(l1, l2, interaction_count)

                # Upsert snapshot row
                existing_result = await session.execute(
                    select(UserCandidateRatingSnapshot).where(
                        UserCandidateRatingSnapshot.viewer_id == viewer.id,
                        UserCandidateRatingSnapshot.candidate_id == candidate.id,
                    )
                )
                snapshot = existing_result.scalar_one_or_none()

                if snapshot is None:
                    snapshot = UserCandidateRatingSnapshot(
                        viewer_id=viewer.id,
                        candidate_id=candidate.id,
                    )
                    session.add(snapshot)

                snapshot.primary_score = l1
                snapshot.behavioral_score = l2
                snapshot.combined_score = combined
                snapshot.computed_at = datetime.utcnow()
                total_snapshots += 1

            await session.commit()

        return {
            "viewers_processed": len(viewers),
            "snapshots_updated": total_snapshots,
            "computed_at": datetime.utcnow().isoformat(),
        }


# ─── Celery tasks ─────────────────────────────────────────────────────────────

@celery_app.task(name="app.tasks.recompute.recompute_behavioral_scores")
def recompute_behavioral_scores() -> dict:
    """
    Periodic Celery task — Level 2 score audit.
    Scheduled by Celery Beat every 30 minutes.
    Computes behavioral scores for all candidates and emits monitoring logs.
    """
    logger.info("[celery] recompute_behavioral_scores: starting")
    result = asyncio.run(_recompute_behavioral_async())
    logger.info(
        f"[celery] recompute_behavioral_scores: done — "
        f"candidates={result['candidates_processed']}"
    )
    return result


@celery_app.task(name="app.tasks.recompute.recompute_combined_snapshots")
def recompute_combined_snapshots() -> dict:
    """
    Periodic Celery task — Level 3 snapshot refresh.
    Scheduled by Celery Beat every hour.
    Pre-computes combined (Level 1 + Level 2) scores for all active
    viewer-candidate pairs and stores them in user_candidate_ratings_snapshot
    so that the recommendation API can rank candidates instantly.
    """
    logger.info("[celery] recompute_combined_snapshots: starting")
    result = asyncio.run(_recompute_snapshots_async())
    logger.info(
        f"[celery] recompute_combined_snapshots: done — "
        f"viewers={result['viewers_processed']}, snapshots={result['snapshots_updated']}"
    )
    return result
