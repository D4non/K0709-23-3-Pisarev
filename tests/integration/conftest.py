"""
Shared fixtures for integration tests.

Strategy:
  - Override get_session → yields AsyncMock (no real DB connection)
  - Override get_redis  → returns FakeRedis (in-memory, no real Redis)
  - Patch create_tables → AsyncMock (prevents lifespan from touching PG)
  - Individual tests patch CRUD/service functions to control return values
"""
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent.parent

for _key in list(sys.modules.keys()):
    if _key == "app" or _key.startswith("app."):
        del sys.modules[_key]

sys.path.insert(0, str(_ROOT / "services" / "profile-service"))

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

import fakeredis.aioredis
from httpx import AsyncClient, ASGITransport

from app.main import app
from app.models.database import get_session, get_redis


def make_mock_user(
    user_id: int = 1,
    telegram_id: int = 111111,
    name: str = "Иван",
    age: int = 25,
    gender: str = "male",
    city: str = "Москва",
    bio: str = "Привет",
    interests: list[str] | None = None,
):
    """Return a lightweight MagicMock that behaves like an ORM User."""
    user = MagicMock()
    user.id = user_id
    user.telegram_id = telegram_id
    user.username = "ivan"

    user.profile = MagicMock()
    user.profile.name = name
    user.profile.age = age
    user.profile.gender = gender
    user.profile.city = city
    user.profile.bio = bio
    user.profile.is_active = True

    _interests = interests or ["музыка", "спорт"]
    user.interests = [MagicMock(interest=i) for i in _interests]
    user.preferences = MagicMock()
    user.preferences.min_age = 18
    user.preferences.max_age = 50
    user.preferences.preferred_gender = None
    user.photos = []
    user.received_interactions = []
    user.given_interactions = []
    return user


@pytest.fixture
async def fake_redis():
    return fakeredis.aioredis.FakeRedis(decode_responses=True)


@pytest.fixture
async def client(fake_redis):
    """
    HTTP client wired to the FastAPI app with DB and Redis dependencies
    replaced by mocks.  create_tables is patched so startup does not
    attempt a real PostgreSQL connection.
    """
    mock_session = AsyncMock()

    async def override_get_session():
        yield mock_session

    async def override_get_redis():
        return fake_redis

    app.dependency_overrides[get_session] = override_get_session
    app.dependency_overrides[get_redis] = override_get_redis

    with patch("app.main.create_tables", new_callable=AsyncMock):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as http:
            yield http

    app.dependency_overrides.clear()
