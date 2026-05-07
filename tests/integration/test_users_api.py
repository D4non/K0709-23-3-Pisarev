"""
Integration tests for POST /users/register and GET /users/{telegram_id}.

DB access is mocked at the CRUD level so no real PostgreSQL is needed.
"""
import pytest
from unittest.mock import AsyncMock, patch

from tests.integration.conftest import make_mock_user

REGISTER_PAYLOAD = {
    "telegram_id": 111111,
    "username": "ivan",
    "name": "Иван",
    "age": 25,
    "gender": "male",
    "city": "Москва",
    "bio": "Привет всем",
    "interests": ["музыка", "спорт"],
    "min_age": 20,
    "max_age": 35,
    "preferred_gender": "female",
}


# ─── POST /users/register ─────────────────────────────────────────────────────

async def test_register_returns_200_and_user_id(client):
    mock_user = make_mock_user(user_id=42, telegram_id=111111)

    with patch("app.api.users.create_or_update_user", new=AsyncMock(return_value=mock_user)):
        resp = await client.post("/users/register", json=REGISTER_PAYLOAD)

    assert resp.status_code == 200
    data = resp.json()
    assert data["user_id"] == 42
    assert data["telegram_id"] == 111111
    assert data["message"] == "ok"


async def test_register_invalid_gender_returns_422(client):
    bad_payload = {**REGISTER_PAYLOAD, "gender": "unknown"}
    resp = await client.post("/users/register", json=bad_payload)
    assert resp.status_code == 422


async def test_register_age_below_minimum_returns_422(client):
    bad_payload = {**REGISTER_PAYLOAD, "age": 15}
    resp = await client.post("/users/register", json=bad_payload)
    assert resp.status_code == 422


async def test_register_name_too_short_returns_422(client):
    bad_payload = {**REGISTER_PAYLOAD, "name": "A"}
    resp = await client.post("/users/register", json=bad_payload)
    assert resp.status_code == 422


# ─── GET /users/{telegram_id} ─────────────────────────────────────────────────

async def test_get_profile_returns_200_with_profile_data(client):
    mock_user = make_mock_user(telegram_id=111111)

    with patch("app.api.users.get_user_by_telegram_id", new=AsyncMock(return_value=mock_user)):
        resp = await client.get("/users/111111")

    assert resp.status_code == 200
    data = resp.json()
    assert data["telegram_id"] == 111111
    assert data["name"] == "Иван"
    assert data["age"] == 25
    assert "музыка" in data["interests"]


async def test_get_profile_unknown_user_returns_404(client):
    with patch("app.api.users.get_user_by_telegram_id", new=AsyncMock(return_value=None)):
        resp = await client.get("/users/999999")

    assert resp.status_code == 404


async def test_get_profile_user_without_profile_returns_404(client):
    mock_user = make_mock_user()
    mock_user.profile = None

    with patch("app.api.users.get_user_by_telegram_id", new=AsyncMock(return_value=mock_user)):
        resp = await client.get("/users/111111")

    assert resp.status_code == 404
