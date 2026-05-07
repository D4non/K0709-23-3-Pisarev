"""
Root conftest: makes shared/ importable from any test file.
Service-specific paths (app.*) are set in each subdirectory's conftest.py
to avoid the app package name collision between profile-service and bot-service.
"""
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent

sys.path.insert(0, str(_ROOT))  # shared/
