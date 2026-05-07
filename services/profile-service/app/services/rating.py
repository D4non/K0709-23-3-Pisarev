"""
Three-level rating algorithm for candidate ranking.

Level 1 (Primary/Static): age compatibility, gender preference, interest overlap,
                           profile completeness. Uses only profile data.
Level 2 (Behavioral):     like ratio and match rate derived from all interactions
                           other users have had with the candidate.
Level 3 (Combined):       weighted blend of Level 1 and Level 2 scores.
"""
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.orm import User, CandidateBehavioralStats, UserCandidateRatingSnapshot
from app.crud.profiles import get_active_candidates
from app.crud.interactions import get_seen_candidate_ids


# ─── Level 1 helpers ─────────────────────────────────────────────────────────

def _gender_score(preferred_gender: str | None, candidate_gender: str) -> float:
    if preferred_gender is None:
        return 0.5  # no preference → neutral
    return 1.0 if candidate_gender == preferred_gender else 0.0


def _age_score(min_age: int, max_age: int, candidate_age: int) -> float:
    if candidate_age < min_age or candidate_age > max_age:
        return 0.0
    if min_age == max_age:
        return 1.0
    # Closer to the centre of preferred range → higher score
    centre = (min_age + max_age) / 2.0
    half_range = (max_age - min_age) / 2.0
    deviation = abs(candidate_age - centre) / half_range
    return max(0.5, 1.0 - deviation * 0.5)


def _interest_score(viewer_interests: list[str], candidate_interests: list[str]) -> float:
    v = {i.lower().strip() for i in viewer_interests if i.strip()}
    c = {i.lower().strip() for i in candidate_interests if i.strip()}
    if not v and not c:
        return 0.5
    union = len(v | c)
    if union == 0:
        return 0.5
    return len(v & c) / union  # Jaccard similarity


def _completeness_score(candidate: User) -> float:
    score = 0.0
    if candidate.profile and candidate.profile.bio:
        score += 0.4
    if candidate.interests:
        score += 0.3
    if candidate.photos:
        score += 0.3
    return score


def calculate_level1(viewer: User, candidate: User) -> float:
    prefs = viewer.preferences
    min_age = prefs.min_age if prefs else 18
    max_age = prefs.max_age if prefs else 99
    preferred_gender = prefs.preferred_gender if prefs else None

    viewer_interests = [i.interest for i in (viewer.interests or [])]
    candidate_interests = [i.interest for i in (candidate.interests or [])]

    g = _gender_score(preferred_gender, candidate.profile.gender)
    a = _age_score(min_age, max_age, candidate.profile.age)
    i = _interest_score(viewer_interests, candidate_interests)
    c = _completeness_score(candidate)

    return 0.35 * g + 0.25 * a + 0.25 * i + 0.15 * c


# ─── Level 2 helpers ─────────────────────────────────────────────────────────

def calculate_level2(received_stats: list[CandidateBehavioralStats]) -> float:
    """
    Scores the candidate based on how all viewers have reacted to their profile.
    Returns 0.5 (neutral) when there is no interaction history yet.
    """
    if not received_stats:
        return 0.5

    total_likes = sum(s.likes_given for s in received_stats)
    total_skips = sum(s.skips_given for s in received_stats)
    total_interactions = total_likes + total_skips

    like_ratio = total_likes / total_interactions if total_interactions > 0 else 0.5
    match_rate = (
        sum(1 for s in received_stats if s.is_matched) / total_likes
        if total_likes > 0
        else 0.5
    )

    return 0.6 * like_ratio + 0.4 * match_rate


# ─── Level 3 ─────────────────────────────────────────────────────────────────

def calculate_combined(level1: float, level2: float, interaction_count: int) -> float:
    """
    Blends Level 1 and Level 2. Weight shifts toward behavioral data as
    interaction_count grows, capping at 60 % behavioral weight after ~50 interactions.
    """
    behavioral_weight = min(0.6, interaction_count / 50 * 0.6)
    static_weight = 1.0 - behavioral_weight
    return static_weight * level1 + behavioral_weight * level2


# ─── Main ranking function ────────────────────────────────────────────────────

async def _get_ranked_from_snapshots(
    session: AsyncSession,
    viewer_user_id: int,
    seen_ids: set[int],
    limit: int,
) -> list[int] | None:
    """
    Fast path: read pre-computed Level 3 scores from the snapshot table.
    Returns None when no snapshots are available (e.g. before the first
    Celery run), so the caller can fall back to real-time computation.
    """
    result = await session.execute(
        select(UserCandidateRatingSnapshot)
        .where(
            UserCandidateRatingSnapshot.viewer_id == viewer_user_id,
            ~UserCandidateRatingSnapshot.candidate_id.in_(seen_ids),
        )
        .order_by(UserCandidateRatingSnapshot.combined_score.desc())
        .limit(limit)
    )
    rows = result.scalars().all()
    if not rows:
        return None
    return [row.candidate_id for row in rows]


async def get_ranked_candidate_ids(
    session: AsyncSession,
    viewer_telegram_id: int,
    viewer_user_id: int,
    limit: int = 10,
) -> list[int]:
    """
    Return up to `limit` candidate user IDs ranked by combined score,
    excluding already-seen profiles.

    Fast path: reads pre-computed snapshots written by the Celery task
    `recompute_combined_snapshots`. Falls back to real-time computation
    when snapshots are not yet available (first run or cache miss).
    """
    from sqlalchemy.orm import selectinload

    seen_ids = await get_seen_candidate_ids(session, viewer_user_id)

    # Try snapshot-based ranking first (pre-computed by Celery)
    snapshot_ids = await _get_ranked_from_snapshots(session, viewer_user_id, seen_ids, limit)
    if snapshot_ids is not None:
        return snapshot_ids

    # Real-time fallback: compute scores on-the-fly
    result = await session.execute(
        select(User)
        .where(User.id == viewer_user_id)
        .options(
            selectinload(User.interests),
            selectinload(User.preferences),
        )
    )
    viewer = result.scalar_one_or_none()
    if viewer is None:
        return []

    candidates = await get_active_candidates(session, viewer_user_id, seen_ids)

    scored: list[tuple[int, float]] = []
    for candidate in candidates:
        if candidate.profile is None:
            continue

        l1 = calculate_level1(viewer, candidate)
        l2 = calculate_level2(candidate.received_interactions)
        interaction_count = sum(
            s.likes_given + s.skips_given for s in candidate.received_interactions
        )
        combined = calculate_combined(l1, l2, interaction_count)
        scored.append((candidate.id, combined))

    scored.sort(key=lambda x: x[1], reverse=True)
    return [uid for uid, _ in scored[:limit]]
