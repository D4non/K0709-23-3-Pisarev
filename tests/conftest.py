"""
Root conftest: makes profile-service, bot-service and shared/ importable
from any test file without manual sys.path manipulation in each file.
"""
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent

sys.path.insert(0, str(_ROOT))                                         # shared/
sys.path.insert(0, str(_ROOT / "services" / "profile-service"))       # app.*
sys.path.insert(0, str(_ROOT / "services" / "bot-service"))           # bot app.*
