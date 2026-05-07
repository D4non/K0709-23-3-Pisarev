"""
HTTP client for media-service.

Handles photo uploads (multipart/form-data) and downloads (proxy to MinIO).
The bot never talks to MinIO directly — all storage I/O goes through media-service,
which runs in the same Docker network.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import aiohttp
from shared.config import settings
from shared.logger import setup_logger

logger = setup_logger("bot-service.media-client")


class MediaClient:
    def __init__(self):
        self._base = settings.MEDIA_SERVICE_URL

    async def upload_photo(
        self,
        telegram_id: int,
        photo_bytes: bytes,
        filename: str = "photo.jpg",
        content_type: str = "image/jpeg",
    ) -> dict:
        """
        Upload raw photo bytes to media-service.
        Returns {"object_key": ..., "url": ...}.
        """
        async with aiohttp.ClientSession() as session:
            form = aiohttp.FormData()
            form.add_field(
                "file",
                photo_bytes,
                filename=filename,
                content_type=content_type,
            )
            async with session.post(
                f"{self._base}/photos/upload",
                params={"telegram_id": telegram_id},
                data=form,
            ) as resp:
                resp.raise_for_status()
                return await resp.json()

    async def get_photo(self, object_key: str) -> bytes:
        """
        Download photo bytes from media-service (proxied from MinIO).
        Used to send the photo to Telegram without exposing MinIO externally.
        """
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{self._base}/photos/{object_key}") as resp:
                resp.raise_for_status()
                return await resp.read()

    async def delete_photo(self, object_key: str) -> None:
        async with aiohttp.ClientSession() as session:
            async with session.delete(
                f"{self._base}/photos/{object_key}"
            ) as resp:
                resp.raise_for_status()
