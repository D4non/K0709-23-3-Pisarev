import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import aiohttp
from shared.config import settings
from shared.logger import setup_logger

logger = setup_logger("bot-service.profile-client")


class ProfileClient:
    def __init__(self):
        self._base = settings.PROFILE_SERVICE_URL

    async def register(
        self,
        telegram_id: int,
        username: str | None,
        name: str,
        age: int,
        gender: str,
        city: str,
        bio: str | None,
        interests: list[str],
    ) -> dict:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self._base}/users/register",
                json={
                    "telegram_id": telegram_id,
                    "username": username,
                    "name": name,
                    "age": age,
                    "gender": gender,
                    "city": city,
                    "bio": bio or None,
                    "interests": interests,
                },
            ) as resp:
                resp.raise_for_status()
                return await resp.json()

    async def get_recommendation(self, telegram_id: int) -> dict | None:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{self._base}/recommendations/{telegram_id}"
            ) as resp:
                if resp.status == 404:
                    return None
                resp.raise_for_status()
                return await resp.json()

    async def record_interaction(
        self,
        viewer_telegram_id: int,
        candidate_telegram_id: int,
        action: str,
    ) -> dict:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self._base}/interactions",
                json={
                    "viewer_telegram_id": viewer_telegram_id,
                    "candidate_telegram_id": candidate_telegram_id,
                    "action": action,
                },
            ) as resp:
                resp.raise_for_status()
                return await resp.json()
