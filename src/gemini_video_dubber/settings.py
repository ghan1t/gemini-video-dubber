from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv


def load_api_key(gui_value: str = "") -> str:
    load_dotenv()
    return os.getenv("GEMINI_API_KEY", "").strip() or gui_value.strip()


def project_root() -> Path:
    return Path(__file__).resolve().parents[2]
