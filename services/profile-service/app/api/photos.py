"""
Photo management API for profile-service.

POST   /photos/{telegram_id}                    — attach uploaded photo to profile
DELETE /photos/{telegram_id}/{photo_id}         — delete photo (DB + MinIO via media-service)
PUT    /photos/{telegram_id}/{photo_id}/primary — set as primary photo
"""
import aiohttp
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.photos import (
    add_photo,
    delete_photo_record,
    get_photo_by_id,
    set_primary_photo,
)
from app.crud.users import get_user_by_telegram_id
from app.models.database import get_session
from app.schemas.user import AddPhotoRequest, PhotoOut
from shared.config import settings
from shared.logger import setup_logger

logger = setup_logger("profile-service.api.photos")
router = APIRouter()


@router.post("/{telegram_id}", response_model=PhotoOut)
async def add_user_photo(
    telegram_id: int,
    body: AddPhotoRequest,
    session: AsyncSession = Depends(get_session),
):
    user = await get_user_by_telegram_id(session, telegram_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    # First photo becomes primary automatically
    is_primary = body.is_primary or len(user.photos) == 0
    photo = await add_photo(session, user.id, body.object_key, body.url, is_primary)

    logger.info(f"Photo added: telegram_id={telegram_id} photo_id={photo.id} primary={is_primary}")
    return PhotoOut(
        id=photo.id,
        url=photo.url,
        object_key=photo.object_key,
        is_primary=photo.is_primary,
    )


@router.delete("/{telegram_id}/{photo_id}")
async def delete_user_photo(
    telegram_id: int,
    photo_id: int,
    session: AsyncSession = Depends(get_session),
):
    user = await get_user_by_telegram_id(session, telegram_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    photo = await get_photo_by_id(session, photo_id, user.id)
    if photo is None:
        raise HTTPException(status_code=404, detail="Photo not found")

    object_key = photo.object_key

    # Remove DB record first
    await delete_photo_record(session, photo)

    # Best-effort: delete from MinIO via media-service
    if object_key:
        async with aiohttp.ClientSession() as http:
            try:
                async with http.delete(
                    f"{settings.MEDIA_SERVICE_URL}/photos/{object_key}"
                ) as resp:
                    if resp.status not in (200, 404):
                        logger.warning(
                            f"media-service DELETE returned {resp.status} for {object_key}"
                        )
            except Exception as exc:
                logger.warning(f"Could not reach media-service for deletion: {exc}")

    logger.info(f"Photo deleted: telegram_id={telegram_id} photo_id={photo_id}")
    return {"message": "deleted", "photo_id": photo_id}


@router.put("/{telegram_id}/{photo_id}/primary")
async def set_primary(
    telegram_id: int,
    photo_id: int,
    session: AsyncSession = Depends(get_session),
):
    user = await get_user_by_telegram_id(session, telegram_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    photo = await set_primary_photo(session, photo_id, user.id)
    if photo is None:
        raise HTTPException(status_code=404, detail="Photo not found")

    return {"message": "primary photo updated", "photo_id": photo_id}
