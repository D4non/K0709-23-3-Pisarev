import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from contextlib import asynccontextmanager
from fastapi import FastAPI

from app.models.database import create_tables
from app.api import users, interactions, recommendations
from shared.logger import setup_logger

logger = setup_logger("profile-service")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting profile-service...")
    await create_tables()
    yield
    logger.info("Shutting down profile-service")


app = FastAPI(title="Dating Profile Service", version="3.0.0", lifespan=lifespan)

app.include_router(users.router, prefix="/users", tags=["users"])
app.include_router(interactions.router, prefix="/interactions", tags=["interactions"])
app.include_router(recommendations.router, prefix="/recommendations", tags=["recommendations"])


@app.get("/health")
async def health():
    return {"status": "ok"}
