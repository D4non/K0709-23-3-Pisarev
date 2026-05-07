"""
Async-friendly MinIO wrapper.

MinIO Python SDK is synchronous, so all I/O calls are dispatched to the
default thread-pool executor via asyncio.get_event_loop().run_in_executor.
This keeps the FastAPI event loop free during uploads/downloads.
"""
import asyncio
import io

from minio import Minio
from minio.error import S3Error

from shared.config import settings
from shared.logger import setup_logger

logger = setup_logger("media-service.minio")

_client: Minio | None = None


def _get_client() -> Minio:
    global _client
    if _client is None:
        _client = Minio(
            settings.MINIO_ENDPOINT,
            access_key=settings.MINIO_ACCESS_KEY,
            secret_key=settings.MINIO_SECRET_KEY,
            secure=False,
        )
    return _client


async def ensure_bucket() -> None:
    """Create the photos bucket if it does not exist yet (called on startup)."""
    client = _get_client()
    loop = asyncio.get_event_loop()

    def _create():
        if not client.bucket_exists(settings.MINIO_BUCKET):
            client.make_bucket(settings.MINIO_BUCKET)
            logger.info(f"Created MinIO bucket: {settings.MINIO_BUCKET}")
        else:
            logger.info(f"MinIO bucket already exists: {settings.MINIO_BUCKET}")

    await loop.run_in_executor(None, _create)


async def upload_file(data: bytes, object_key: str, content_type: str) -> str:
    """
    Upload raw bytes to MinIO and return the internal URL.
    The URL uses the Docker-internal hostname (minio:9000) — the bot
    downloads photos through the media-service proxy endpoint instead.
    """
    client = _get_client()
    loop = asyncio.get_event_loop()

    def _upload():
        client.put_object(
            settings.MINIO_BUCKET,
            object_key,
            io.BytesIO(data),
            length=len(data),
            content_type=content_type,
        )

    await loop.run_in_executor(None, _upload)

    url = f"http://{settings.MINIO_ENDPOINT}/{settings.MINIO_BUCKET}/{object_key}"
    logger.info(f"Uploaded {object_key} ({len(data)} bytes) → {url}")
    return url


async def delete_file(object_key: str) -> None:
    """Remove an object from MinIO."""
    client = _get_client()
    loop = asyncio.get_event_loop()

    def _delete():
        client.remove_object(settings.MINIO_BUCKET, object_key)

    await loop.run_in_executor(None, _delete)
    logger.info(f"Deleted {object_key} from MinIO")


async def get_file(object_key: str) -> bytes:
    """
    Download an object from MinIO and return its bytes.
    Used by the GET /photos/{object_key} proxy endpoint so the Telegram bot
    can fetch photos through the Docker-internal network.
    """
    client = _get_client()
    loop = asyncio.get_event_loop()

    def _download() -> bytes:
        response = client.get_object(settings.MINIO_BUCKET, object_key)
        try:
            return response.read()
        finally:
            response.close()
            response.release_conn()

    return await loop.run_in_executor(None, _download)
