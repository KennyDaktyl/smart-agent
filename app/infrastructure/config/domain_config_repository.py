import errno
import json
import os
from pathlib import Path
from typing import Any, Optional

from app.core.config import settings
from app.core.logging_config import logger
from app.domain.models.agent_config import AgentConfig, DeviceMode


class DomainConfigRepository:

    def __init__(self):
        self._config: Optional[AgentConfig] = None
        self._config_path = self._resolve_path()

    def _resolve_path(self) -> Path:
        path = Path(settings.CONFIG_FILE)

        if not path.is_absolute():
            path = settings.BASE_DIR / path

        return path

    def load(self) -> AgentConfig:
        if self._config is not None:
            return self._config

        if not self._config_path.exists():
            raise FileNotFoundError(f"Domain config not found: {self._config_path}")

        logger.info(f"Loading domain config: {self._config_path}")

        with self._config_path.open("r", encoding="utf-8") as f:
            raw = json.load(f)

        raw = self._normalize_legacy_fields(raw)
        raw = self._normalize_heartbeat(raw)

        if "devices" in raw:
            raw["devices"] = self._normalize_devices(raw["devices"])

        self._config = AgentConfig(**raw)
        return self._config

    @staticmethod
    def _normalize_legacy_fields(raw: dict) -> dict:
        if not isinstance(raw, dict):
            raise ValueError("Domain config root must be an object")

        normalized = dict(raw)
        if "active_low" in normalized:
            logger.warning(
                "Legacy top-level 'active_low' in domain config is ignored. "
                "Use per-device 'active_low' in hardware_config.json."
            )
            normalized.pop("active_low", None)

        return normalized

    @staticmethod
    def _normalize_heartbeat(raw: dict) -> dict:
        if not isinstance(raw, dict):
            raise ValueError("Domain config root must be an object")

        normalized = dict(raw)
        if "heartbeat_interval" in normalized:
            return normalized

        heartbeat = normalized.get("heartbeat")
        if isinstance(heartbeat, dict) and "interval" in heartbeat:
            normalized["heartbeat_interval"] = heartbeat["interval"]
            logger.warning(
                "Legacy 'heartbeat.interval' detected in config. "
                "Using it as 'heartbeat_interval'."
            )
            return normalized

        return normalized

    def _normalize_devices(self, devices: Any) -> dict[int, dict]:
        if not isinstance(devices, dict):
            raise ValueError("'devices' must be a dictionary")

        normalized: dict[int, dict] = {}

        for key, value in devices.items():
            device_number = int(key)
            if not isinstance(value, dict):
                raise ValueError(
                    f"Device config for key={device_number} must be an object"
                )

            payload = dict(value)
            mode_value = str(payload.get("mode"))
            device_uuid = payload.get("device_uuid")

            if "threshold_value" not in payload:
                if "threshold_kw" in payload:
                    payload["threshold_value"] = payload.pop("threshold_kw")

            payload.pop("threshold_kw", None)
            payload["device_number"] = device_number

            if device_uuid is None or not str(device_uuid).strip():
                raise ValueError(
                    f"Device config key={device_number} missing required device_uuid"
                )
            payload["device_uuid"] = str(device_uuid).strip()

            if mode_value == DeviceMode.MANUAL.value:
                if payload.get("desired_state") is None and "is_on" in payload:
                    payload["desired_state"] = bool(payload.get("is_on"))
                if payload.get("desired_state") is None:
                    payload["desired_state"] = False
            else:
                payload["desired_state"] = None

            payload.pop("is_on", None)

            normalized[device_number] = payload

        return normalized

    def save(self) -> None:
        if self._config is None:
            raise RuntimeError("Cannot save before load()")

        tmp_path = self._config_path.with_suffix(".tmp")

        data = self._config.model_dump()

        data["devices"] = {str(k): v for k, v in data["devices"].items()}
        from app.infrastructure.gpio.gpio_manager import gpio_manager

        for key, device in data["devices"].items():
            device_number = int(key)
            runtime_device = gpio_manager.get_by_number(device_number)
            mode_value = str(device.get("mode"))

            if runtime_device:
                device["is_on"] = gpio_manager.read_is_on_by_number(device_number)
            elif mode_value == DeviceMode.MANUAL.value:
                device["is_on"] = bool(device.get("desired_state"))
            else:
                device["is_on"] = False

        self._write_json_with_fallback(data=data, tmp_path=tmp_path)

    def _write_json_with_fallback(self, *, data: dict, tmp_path: Path) -> None:
        with tmp_path.open("w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
            f.flush()
            os.fsync(f.fileno())

        try:
            tmp_path.replace(self._config_path)
            logger.info("Domain config saved (atomic write)")
            return
        except OSError as exc:
            if exc.errno not in {errno.EBUSY, errno.EXDEV, errno.EPERM}:
                raise

            logger.warning(
                "Atomic replace failed for domain config (%s). "
                "Falling back to in-place write: %s",
                self._config_path,
                exc,
            )

        with self._config_path.open("w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
            f.flush()
            os.fsync(f.fileno())

        try:
            tmp_path.unlink(missing_ok=True)
        except Exception:
            logger.debug("Failed to remove temp config file: %s", tmp_path)

        logger.info("Domain config saved (in-place write)")

    def update(self, **kwargs) -> AgentConfig:
        config = self.load()
        current_data = config.model_dump(mode="python")
        merged_data = {**current_data, **kwargs}
        self._config = AgentConfig.model_validate(merged_data)
        self.save()
        return self._config

    def reload(self) -> AgentConfig:
        self._config = None
        return self.load()


domain_config_repository = DomainConfigRepository()
