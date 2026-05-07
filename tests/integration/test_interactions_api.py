"""
Integration tests for POST /interactions.

Covers: like without match, like with mutual match, skip, unknown users.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from tests.integration.conftest import make_mock_user

INTERACTION_URL = "/interactions"


def _like_payload(viewer_tid=111, candidate_tid=222):
    return {
        "viewer_telegram_id": viewer_tid,
        "candidate_telegram_id": candidate_tid,
        "action": "like",
    }


def _skip_payload(viewer_tid=111, candidate_tid=222):
    return {
        "viewer_telegram_id": viewer_tid,
        "candidate_telegram_id": candidate_tid,
        "action": "skip",
    }


# ─── like (no match) ──────────────────────────────────────────────────────────

async def test_like_no_match_returns_success(client):
    viewer = make_mock_user(user_id=1, telegram_id=111)
    candidate = make_mock_user(user_id=2, telegram_id=222, name="Анна", gender="female")

    mock_stats = MagicMock()

    with (
        patch("app.api.interactions.get_user_by_telegram_id", new=AsyncMock(side_effect=[viewer, candidate])),
        patch("app.api.interactions.record_like", new=AsyncMock(return_value=(mock_stats, False))),
    ):
        resp = await client.post(INTERACTION_URL, json=_like_payload())

    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["is_match"] is False
    assert data["candidate_name"] is None


# ─── like (mutual match) ──────────────────────────────────────────────────────

async def test_like_with_match_invalidates_cache_and_returns_names(client):
    viewer = make_mock_user(user_id=1, telegram_id=111, name="Иван")
    candidate = make_mock_user(user_id=2, telegram_id=222, name="Анна")

    mock_stats = MagicMock()

    with (
        patch("app.api.interactions.get_user_by_telegram_id", new=AsyncMock(side_effect=[viewer, candidate])),
        patch("app.api.interactions.record_like", new=AsyncMock(return_value=(mock_stats, True))),
        patch("app.api.interactions.invalidate", new=AsyncMock()) as mock_invalidate,
    ):
        resp = await client.post(INTERACTION_URL, json=_like_payload(111, 222))

    assert resp.status_code == 200
    data = resp.json()
    assert data["is_match"] is True
    assert data["candidate_name"] == "Анна"
    assert data["viewer_name"] == "Иван"
    # Both caches must be invalidated
    assert mock_invalidate.call_count == 2


# ─── skip ─────────────────────────────────────────────────────────────────────

async def test_skip_returns_success_no_match(client):
    viewer = make_mock_user(user_id=1, telegram_id=111)
    candidate = make_mock_user(user_id=2, telegram_id=222)

    mock_stats = MagicMock()

    with (
        patch("app.api.interactions.get_user_by_telegram_id", new=AsyncMock(side_effect=[viewer, candidate])),
        patch("app.api.interactions.record_skip", new=AsyncMock(return_value=mock_stats)),
    ):
        resp = await client.post(INTERACTION_URL, json=_skip_payload())

    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["is_match"] is False


# ─── validation / 404 errors ──────────────────────────────────────────────────

async def test_interaction_invalid_action_returns_422(client):
    resp = await client.post(INTERACTION_URL, json={
        "viewer_telegram_id": 111,
        "candidate_telegram_id": 222,
        "action": "poke",  # not in ^(like|skip)$
    })
    assert resp.status_code == 422


async def test_interaction_viewer_not_found_returns_404(client):
    with patch("app.api.interactions.get_user_by_telegram_id", new=AsyncMock(return_value=None)):
        resp = await client.post(INTERACTION_URL, json=_like_payload())
    assert resp.status_code == 404


async def test_interaction_candidate_not_found_returns_404(client):
    viewer = make_mock_user(user_id=1, telegram_id=111)

    with patch(
        "app.api.interactions.get_user_by_telegram_id",
        new=AsyncMock(side_effect=[viewer, None]),
    ):
        resp = await client.post(INTERACTION_URL, json=_like_payload())
    assert resp.status_code == 404
