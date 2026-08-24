from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

os.environ.setdefault("TG_BOT_TOKEN", "12345:SMOKE_TEST_TOKEN_PLACEHOLDER_12345")
os.environ.setdefault("DATA_DIR", str(ROOT / "data"))
