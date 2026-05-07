import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from contextlib import asynccontextmanager
from fastapi import FastAPI

from app.api.photos import router as photos_router
from app.services.minio_client import ensure_bucket
from shared.logger import setup_logger

logger = setup_logger("media-service")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting media-service, initialising MinIO bucket...")
    await ensure_bucket()
    yield
    logger.info("Shutting down media-service")


app = FastAPI(title="Dating Media Service", version="1.0.0", lifespan=lifespan)

app.include_router(photos_router, prefix="/photos", tags=["photos"])


@app.get("/health")
async def health():
    return {"status": "ok"}
