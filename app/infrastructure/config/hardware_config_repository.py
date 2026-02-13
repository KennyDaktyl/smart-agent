import json
from pathlib import Path
from typing import Optional

from app.core.config import settings
from app.core.logging_config import logger
from app.domain.models.hardware_config import HardwareConfig


class HardwareConfigRepository:

    def __init__(self):
        self._config: Optional[HardwareConfig] = None
        self._config_path = self._resolve_path()

    def _resolve_path(self) -> Path:
        path = settings.BASE_DIR / "hardware_config.json"
        return path

    def load(self) -> HardwareConfig:
        if self._config is not None:
            return self._config

        if not self._config_path.exists():
            raise FileNotFoundError(
                f"Hardware config not found: {self._config_path}"
            )

        logger.info(f"Loading hardware config: {self._config_path}")

        with self._config_path.open("r", encoding="utf-8") as f:
            raw = json.load(f)

        if "devices" in raw:
            raw["devices"] = {
                int(k): v for k, v in raw["devices"].items()
            }

        self._config = HardwareConfig(**raw)
        return self._config

    def save(self) -> None:
        if self._config is None:
            raise RuntimeError("Cannot save before load()")

        tmp_path = self._config_path.with_suffix(".tmp")

        data = self._config.model_dump()

        data["devices"] = {
            str(k): v for k, v in data["devices"].items()
        }

        with tmp_path.open("w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

        tmp_path.replace(self._config_path)

        logger.info("Hardware config saved (atomic write)")

    def reload(self) -> HardwareConfig:
        self._config = None
        return self.load()


hardware_config_repository = HardwareConfigRepository()
