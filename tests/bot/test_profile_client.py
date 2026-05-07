"""
Bot unit tests — ProfileClient HTTP wrapper (app/services/profile_client.py).

All HTTP calls are intercepted with unittest.mock so no real network or
profile-service is needed. Tests verify that the client sends the right
payload and correctly handles responses.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.profile_client import ProfileClient


def _mock_aiohttp_session(status: int, json_body: dict):
    """
    Build a mock that replicates the aiohttp.ClientSession context-manager
    protocol used inside ProfileClient methods.
    """
    mock_response = AsyncMock()
    mock_response.status = status
    mock_response.json = AsyncMock(return_value=json_body)
    mock_response.raise_for_status = MagicMock()

    mock_resp_cm = AsyncMock()
    mock_resp_cm.__aenter__ = AsyncMock(return_value=mock_response)
    mock_resp_cm.__aexit__ = AsyncMock(return_value=False)

    mock_session = MagicMock()
    mock_session.post.return_value = mock_resp_cm
    mock_session.get.return_value = mock_resp_cm

    mock_session_cm = AsyncMock()
    mock_session_cm.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session_cm.__aexit__ = AsyncMock(return_value=False)

    return mock_session_cm, mock_session, mock_response


# ─── register ─────────────────────────────────────────────────────────────────

async def test_register_returns_parsed_json():
    expected = {"user_id": 7, "telegram_id": 123456, "message": "ok"}
    session_cm, mock_session, _ = _mock_aiohttp_session(200, expected)

    with patch("aiohttp.ClientSession", return_value=session_cm):
        client = ProfileClient()
        result = await client.register(
            telegram_id=123456,
            username="test",
            name="Тест",
            age=25,
            gender="male",
            city="Москва",
            bio="Привет",
            interests=["музыка"],
        )

    assert result == expected
    mock_session.post.assert_called_once()


async def test_register_posts_to_correct_endpoint():
    session_cm, mock_session, _ = _mock_aiohttp_session(200, {"user_id": 1, "message": "ok", "telegram_id": 1})

    with patch("aiohttp.ClientSession", return_value=session_cm):
        client = ProfileClient()
        await client.register(
            telegram_id=1, username=None, name="A", age=20,
            gender="female", city="City", bio=None, interests=[],
        )

    call_args = mock_session.post.call_args
    assert "/users/register" in call_args[0][0]


# ─── get_recommendation ───────────────────────────────────────────────────────

async def test_get_recommendation_returns_profile_dict():
    profile = {"telegram_id": 999, "name": "Мария", "age": 22, "gender": "female",
               "city": "СПб", "bio": None, "interests": []}
    session_cm, _, _ = _mock_aiohttp_session(200, profile)

    with patch("aiohttp.ClientSession", return_value=session_cm):
        client = ProfileClient()
        result = await client.get_recommendation(telegram_id=111)

    assert result == profile


async def test_get_recommendation_returns_none_on_404():
    session_cm, mock_session, mock_response = _mock_aiohttp_session(404, {})
    mock_response.status = 404

    with patch("aiohttp.ClientSession", return_value=session_cm):
        client = ProfileClient()
        result = await client.get_recommendation(telegram_id=111)

    assert result is None


# ─── record_interaction ───────────────────────────────────────────────────────

async def test_record_interaction_like():
    expected = {"success": True, "is_match": False}
    session_cm, mock_session, _ = _mock_aiohttp_session(200, expected)

    with patch("aiohttp.ClientSession", return_value=session_cm):
        client = ProfileClient()
        result = await client.record_interaction(
            viewer_telegram_id=111,
            candidate_telegram_id=222,
            action="like",
        )

    assert result["success"] is True
    payload = mock_session.post.call_args[1]["json"]
    assert payload["action"] == "like"
    assert payload["viewer_telegram_id"] == 111
    assert payload["candidate_telegram_id"] == 222


async def test_record_interaction_match_response():
    expected = {"success": True, "is_match": True, "candidate_name": "Анна", "viewer_name": "Иван"}
    session_cm, _, _ = _mock_aiohttp_session(200, expected)

    with patch("aiohttp.ClientSession", return_value=session_cm):
        client = ProfileClient()
        result = await client.record_interaction(111, 222, "like")

    assert result["is_match"] is True
    assert result["candidate_name"] == "Анна"
