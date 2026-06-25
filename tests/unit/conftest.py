import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent.parent

for _key in list(sys.modules.keys()):
    if _key == "app" or _key.startswith("app."):
        del sys.modules[_key]

sys.path.insert(0, str(_ROOT / "services" / "profile-service"))
