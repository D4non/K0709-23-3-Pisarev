"""
Unit tests for the Redis recommendation cache (app/services/cache.py).

Uses fakeredis so tests run without a real Redis instance.
fakeredis.aioredis.FakeRedis mimics redis.asyncio.Redis behaviour exactly.
"""
import pytest
import fakeredis.aioredis

from app.services.cache import (
    pop_candidate,
    push_candidates,
    queue_length,
    invalidate,
)


@pytest.fixture
async def redis():
    return fakeredis.aioredis.FakeRedis(decode_responses=True)


# ─── push_candidates / pop_candidate ──────────────────────────────────────────

async def test_push_and_pop_returns_first_candidate(redis):
    """Best candidate (index 0) should be popped first."""
    await push_candidates(redis, telegram_id=111, candidate_ids=[10, 20, 30])
    first = await pop_candidate(redis, telegram_id=111)
    assert first == 10


async def test_pop_all_in_ranked_order(redis):
    await push_candidates(redis, telegram_id=111, candidate_ids=[1, 2, 3])
    results = []
    for _ in range(3):
        results.append(await pop_candidate(redis, telegram_id=111))
    assert results == [1, 2, 3]


async def test_pop_from_empty_queue_returns_none(redis):
    result = await pop_candidate(redis, telegram_id=99999)
    assert result is None


async def test_push_overwrites_existing_queue(redis):
    await push_candidates(redis, telegram_id=111, candidate_ids=[1, 2])
    await push_candidates(redis, telegram_id=111, candidate_ids=[10, 20, 30])
    length = await queue_length(redis, telegram_id=111)
    assert length == 3


# ─── queue_length ─────────────────────────────────────────────────────────────

async def test_queue_length_after_push(redis):
    await push_candidates(redis, telegram_id=222, candidate_ids=[5, 6, 7, 8])
    assert await queue_length(redis, telegram_id=222) == 4


async def test_queue_length_decreases_on_pop(redis):
    await push_candidates(redis, telegram_id=333, candidate_ids=[1, 2, 3])
    await pop_candidate(redis, telegram_id=333)
    assert await queue_length(redis, telegram_id=333) == 2


async def test_queue_length_empty_is_zero(redis):
    assert await queue_length(redis, telegram_id=0) == 0


# ─── invalidate ───────────────────────────────────────────────────────────────

async def test_invalidate_empties_queue(redis):
    await push_candidates(redis, telegram_id=444, candidate_ids=[1, 2, 3])
    await invalidate(redis, telegram_id=444)
    assert await queue_length(redis, telegram_id=444) == 0


async def test_invalidate_non_existing_key_is_safe(redis):
    await invalidate(redis, telegram_id=99999)  # must not raise


# ─── isolation between users ──────────────────────────────────────────────────

async def test_different_users_have_independent_queues(redis):
    await push_candidates(redis, telegram_id=1, candidate_ids=[100, 200])
    await push_candidates(redis, telegram_id=2, candidate_ids=[300, 400])

    await invalidate(redis, telegram_id=1)

    assert await queue_length(redis, telegram_id=1) == 0
    assert await queue_length(redis, telegram_id=2) == 2
