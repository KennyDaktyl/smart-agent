import json
from pathlib import Path
from typing import Any, Dict

from app.core.config import settings
from app.core.logging_config import logging

logger = logging.getLogger(__name__)

_CONFIG_CACHE: Dict[str, Any] | None = None


def load_device_config() -> Dict[str, Any]:
    global _CONFIG_CACHE

    if _CONFIG_CACHE is not None:
        return _CONFIG_CACHE

    config_path = Path(settings.CONFIG_FILE)

    if not config_path.exists():
        raise FileNotFoundError(f"Device config not found: {config_path}")

    logger.info(f"Loading device config from: {config_path}")

    with config_path.open("r", encoding="utf-8") as f:
        _CONFIG_CACHE = json.load(f)

    return _CONFIG_CACHE


def get_microcontroller_uuid() -> str:
    cfg = load_device_config()
    uuid = cfg.get("microcontroller_uuid")

    if not uuid:
        raise RuntimeError("microcontroller_uuid missing in config.json")

    return uuid
