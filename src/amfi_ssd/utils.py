from __future__ import annotations

import re
from pathlib import Path


_INVALID_FILENAME_CHARS = re.compile(r'[\\/:*?"<>|]+')
_WHITESPACE = re.compile(r"\s+")


def sanitize_filename(value: str, fallback: str = "unknown") -> str:
    value = (value or "").strip()
    value = _INVALID_FILENAME_CHARS.sub("_", value)
    value = _WHITESPACE.sub("_", value)
    value = re.sub(r"_+", "_", value)
    value = value.strip("._ ")
    return value or fallback


def ensure_directory(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path
