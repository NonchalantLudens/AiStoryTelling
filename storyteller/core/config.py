"""config.yaml 装载。"""
from pathlib import Path
from typing import Any

import yaml

DEFAULT_PATH = Path("config.yaml")


def load_config(path: Path = DEFAULT_PATH) -> dict[str, Any]:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}
