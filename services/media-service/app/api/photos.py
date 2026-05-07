"""
Photo upload / download / delete API.

POST   /photos/upload              — upload file, store in MinIO, return key+url
GET    /photos/{object_key}        — proxy: stream photo bytes (used by bot)
DELETE /photos/{object_key}        — delete from MinIO
"""
import uuid

from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from fastapi.responses import Response
from minio.error import S3Error

from app.schemas.photo import PhotoUploadResponse
from app.services.minio_client import delete_file, get_file, upload_file
from shared.logger import setup_logger

logger = setup_logger("media-service.api.photos")
router = APIRouter()

_ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}


@router.post("/upload", response_model=PhotoUploadResponse)
async def upload_photo(
    telegram_id: int = Query(..., description="Owner's Telegram ID"),
    file: UploadFile = File(...),
):
    if file.content_type not in _ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type: {file.content_type}. Allowed: {_ALLOWED_CONTENT_TYPES}",
        )

    ext = (file.filename or "photo.jpg").rsplit(".", 1)[-1].lower()
    object_key = f"photos/{telegram_id}/{uuid.uuid4().hex}.{ext}"

    data = await file.read()
    if len(data) > 10 * 1024 * 1024:  # 10 MB limit
        raise HTTPException(status_code=413, detail="File too large (max 10 MB)")

    url = await upload_file(data, object_key, file.content_type)

    logger.info(f"Photo uploaded: telegram_id={telegram_id} key={object_key}")
    return PhotoUploadResponse(object_key=object_key, url=url)


@router.get("/{object_key:path}")
async def get_photo(object_key: str):
    """
    Proxy endpoint: downloads photo from MinIO and streams it back.
    The bot uses this to download photos without needing direct MinIO access.
    """
    try:
        data = await get_file(object_key)
    except S3Error as exc:
        raise HTTPException(status_code=404, detail=f"Photo not found: {exc}")
    except Exception as exc:
        logger.error(f"Failed to fetch {object_key}: {exc}")
        raise HTTPException(status_code=500, detail="Storage error")

    return Response(content=data, media_type="image/jpeg")


@router.delete("/{object_key:path}")
async def delete_photo(object_key: str):
    try:
        await delete_file(object_key)
    except S3Error as exc:
        raise HTTPException(status_code=404, detail=f"Photo not found: {exc}")
    except Exception as exc:
        logger.error(f"Failed to delete {object_key}: {exc}")
        raise HTTPException(status_code=500, detail="Storage error")

    return {"message": "deleted", "object_key": object_key}
