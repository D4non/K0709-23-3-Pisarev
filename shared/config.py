"""
Application settings loaded from environment variables.
"""
import os
from pathlib import Path
from dotenv import load_dotenv

# .env is at the project root, find it relative to this file
_env_path = Path(__file__).resolve().parents[1] / ".env"
load_dotenv(dotenv_path=_env_path)


class Settings:
    BOT_TOKEN = os.getenv("BOT_TOKEN", "")
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")


settings = Settings()
