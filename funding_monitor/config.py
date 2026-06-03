from __future__ import annotations

import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR = ROOT / "config"
DATA_DIR = ROOT / "data"
DOCS_DIR = ROOT / "docs"


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def load_profiles() -> list[dict[str, Any]]:
    return load_json(CONFIG_DIR / "profiles.json")["profiles"]


def load_sources() -> dict[str, Any]:
    return load_json(CONFIG_DIR / "sources.json")
