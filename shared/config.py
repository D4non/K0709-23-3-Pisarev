"""
Application settings loaded from environment variables.
"""
import os
from pathlib import Path
from dotenv import load_dotenv

_env_path = Path(__file__).resolve().parents[1] / ".env"
load_dotenv(dotenv_path=_env_path)


class Settings:
    BOT_TOKEN = os.getenv("BOT_TOKEN", "")
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

    DATABASE_URL = os.getenv(
        "DATABASE_URL",
        "postgresql+asyncpg://dating_user:dating_pass@postgres:5432/dating_db",
    )
    REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
    PROFILE_SERVICE_URL = os.getenv("PROFILE_SERVICE_URL", "http://profile-service:8000")
    MEDIA_SERVICE_URL = os.getenv("MEDIA_SERVICE_URL", "http://media-service:8001")

    # MinIO / S3-compatible object storage
    MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "minio:9000")
    MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", "minioadmin")
    MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY", "minioadmin")
    MINIO_BUCKET = os.getenv("MINIO_BUCKET", "dating-photos")


settings = Settings()
