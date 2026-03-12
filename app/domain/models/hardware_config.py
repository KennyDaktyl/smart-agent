from typing import Any, Dict

from pydantic import BaseModel, Field, field_validator

from app.domain.models.sensor import HardwareSensorConfig


class HardwareDeviceConfig(BaseModel):
    gpio: int
    active_low: bool


class HardwareConfig(BaseModel):
    config_version: int = 2
    devices: Dict[int, HardwareDeviceConfig]
    sensors: Dict[str, HardwareSensorConfig] = Field(default_factory=dict)

    @field_validator("sensors", mode="before")
    @classmethod
    def normalize_sensors(cls, value: Any) -> Dict[str, dict]:
        if value is None:
            return {}

        if isinstance(value, dict):
            normalized: Dict[str, dict] = {}
            for sensor_id, config in value.items():
                if not isinstance(config, dict):
                    raise ValueError("sensor config entries must be objects")
                normalized[str(sensor_id)] = {
                    "sensor_id": str(sensor_id),
                    **config,
                }
            return normalized

        if isinstance(value, list):
            normalized = {}
            for config in value:
                if not isinstance(config, dict):
                    raise ValueError("sensor config entries must be objects")
                sensor_id = str(config.get("sensor_id", "")).strip()
                if not sensor_id:
                    raise ValueError("sensor_id is required for each sensor")
                normalized[sensor_id] = {
                    "sensor_id": sensor_id,
                    **config,
                }
            return normalized

        raise ValueError("sensors must be an object or a list")
