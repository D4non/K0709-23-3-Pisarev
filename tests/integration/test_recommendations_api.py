"""
Integration tests for GET /recommendations/{telegram_id}
and POST /recommendations/{telegram_id}/refresh.
"""
import pytest
from unittest.mock import AsyncMock, patch

from tests.integration.conftest import make_mock_user


# ─── GET /recommendations/{telegram_id} ───────────────────────────────────────

async def test_get_recommendation_returns_candidate_profile(client):
    viewer = make_mock_user(user_id=1, telegram_id=111)
    candidate = make_mock_user(user_id=2, telegram_id=222, name="Анна", age=23, gender="female")

    with (
        patch("app.api.recommendations.get_user_by_telegram_id", new=AsyncMock(return_value=viewer)),
        patch("app.api.recommendations.get_or_compute_next", new=AsyncMock(return_value=2)),
        patch("app.api.recommendations._fetch_user_by_id", new=AsyncMock(return_value=candidate)),
    ):
        resp = await client.get("/recommendations/111")

    assert resp.status_code == 200
    data = resp.json()
    assert data["telegram_id"] == 222
    assert data["name"] == "Анна"
    assert data["age"] == 23
    assert data["gender"] == "female"


async def test_get_recommendation_viewer_not_found_returns_404(client):
    with patch("app.api.recommendations.get_user_by_telegram_id", new=AsyncMock(return_value=None)):
        resp = await client.get("/recommendations/999")
    assert resp.status_code == 404


async def test_get_recommendation_viewer_has_no_profile_returns_404(client):
    viewer = make_mock_user()
    viewer.profile = None

    with patch("app.api.recommendations.get_user_by_telegram_id", new=AsyncMock(return_value=viewer)):
        resp = await client.get("/recommendations/111")
    assert resp.status_code == 404


async def test_get_recommendation_no_candidates_returns_404(client):
    viewer = make_mock_user(user_id=1, telegram_id=111)

    with (
        patch("app.api.recommendations.get_user_by_telegram_id", new=AsyncMock(return_value=viewer)),
        patch("app.api.recommendations.get_or_compute_next", new=AsyncMock(return_value=None)),
    ):
        resp = await client.get("/recommendations/111")
    assert resp.status_code == 404


# ─── POST /recommendations/{telegram_id}/refresh ──────────────────────────────

async def test_refresh_recommendations_clears_cache(client, fake_redis):
    """Refresh should delete the viewer's Redis cache key."""
    import fakeredis.aioredis
    from app.services.cache import push_candidates, queue_length

    # Pre-fill cache
    await push_candidates(fake_redis, telegram_id=111, candidate_ids=[1, 2, 3])
    assert await queue_length(fake_redis, telegram_id=111) == 3

    resp = await client.post("/recommendations/111/refresh")

    assert resp.status_code == 200
    # Cache should be empty after refresh
    assert await queue_length(fake_redis, telegram_id=111) == 0
