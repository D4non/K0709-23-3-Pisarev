"""
Redis-based recommendation cache.

Per-user list of candidate user_ids (strings).
- Pop from right to get next candidate.
- Refill with a fresh ranked batch when fewer than 3 remain.
- TTL 1 hour; invalidated when a match is detected.
"""
import asyncio

import redis.asyncio as aioredis
from sqlalchemy.ext.asyncio import AsyncSession

from shared.logger import setup_logger

logger = setup_logger("profile-service.cache")

_CACHE_TTL = 3600
_REFILL_THRESHOLD = 3
_BATCH_SIZE = 10


def _key(telegram_id: int) -> str:
    return f"recommendations:{telegram_id}"


async def pop_candidate(redis: aioredis.Redis, telegram_id: int) -> int | None:
    raw = await redis.rpop(_key(telegram_id))
    return int(raw) if raw is not None else None


async def queue_length(redis: aioredis.Redis, telegram_id: int) -> int:
    return await redis.llen(_key(telegram_id))


async def push_candidates(
    redis: aioredis.Redis, telegram_id: int, candidate_ids: list[int]
) -> None:
    if not candidate_ids:
        return
    key = _key(telegram_id)
    await redis.delete(key)
    await redis.lpush(key, *[str(cid) for cid in candidate_ids])
    await redis.expire(key, _CACHE_TTL)
    logger.info(f"Pushed {len(candidate_ids)} candidates to cache for telegram_id={telegram_id}")


async def invalidate(redis: aioredis.Redis, telegram_id: int) -> None:
    await redis.delete(_key(telegram_id))


async def get_or_compute_next(
    redis: aioredis.Redis,
    session: AsyncSession,
    telegram_id: int,
    viewer_user_id: int,
) -> int | None:
    from app.services.rating import get_ranked_candidate_ids

    candidate_id = await pop_candidate(redis, telegram_id)

    if candidate_id is None:
        ranked = await get_ranked_candidate_ids(session, telegram_id, viewer_user_id, limit=_BATCH_SIZE)
        if not ranked:
            return None
        if len(ranked) > 1:
            await push_candidates(redis, telegram_id, ranked[1:])
        return ranked[0]

    remaining = await queue_length(redis, telegram_id)
    if remaining < _REFILL_THRESHOLD:
        # Background refill uses its own session to avoid lifecycle conflicts.
        asyncio.create_task(
            _background_refill(redis, telegram_id, viewer_user_id)
        )

    return candidate_id


async def _background_refill(
    redis: aioredis.Redis,
    telegram_id: int,
    viewer_user_id: int,
) -> None:
    from app.models.database import AsyncSessionLocal
    from app.services.rating import get_ranked_candidate_ids
    try:
        async with AsyncSessionLocal() as session:
            ranked = await get_ranked_candidate_ids(
                session, telegram_id, viewer_user_id, limit=_BATCH_SIZE
            )
            if ranked:
                await push_candidates(redis, telegram_id, ranked)
    except Exception as exc:
        logger.warning(f"Background refill failed for telegram_id={telegram_id}: {exc}")
