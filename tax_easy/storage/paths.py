"""OS-standard path resolution for cached rules and persisted user data."""

from __future__ import annotations

from pathlib import Path

import platformdirs

APP_NAME = "tax-easy"
APP_AUTHOR = "tax-easy"


def cache_dir() -> Path:
    path = Path(platformdirs.user_cache_dir(APP_NAME, APP_AUTHOR)) / "rules"
    path.mkdir(parents=True, exist_ok=True)
    return path


def data_dir() -> Path:
    path = Path(platformdirs.user_data_dir(APP_NAME, APP_AUTHOR))
    path.mkdir(parents=True, exist_ok=True)
    return path


def rules_cache_path(year: int) -> Path:
    return cache_dir() / f"{year}.json"


def input_data_path(year: int, filing_status: str) -> Path:
    return data_dir() / f"{year}-{filing_status}.json"
