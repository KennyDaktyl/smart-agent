from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class SensorType(str, Enum):
    DS18B20 = "ds18b20"


class SensorStatus(str, Enum):
    OK = "OK"
    ERROR = "ERROR"


class TemperatureControlConfig(BaseModel):
    enabled: bool = False
    sensor_id: str | None = None
    target_temperature_c: float | None = None
    stop_above_target_delta_c: float = 2.0
    start_below_target_delta_c: float = 3.0

    @field_validator("sensor_id")
    @classmethod
    def validate_sensor_id(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @field_validator(
        "stop_above_target_delta_c",
        "start_below_target_delta_c",
    )
    @classmethod
    def validate_delta(cls, value: float) -> float:
        if value < 0:
            raise ValueError("temperature control deltas must be >= 0")
        return value

    @model_validator(mode="after")
    def validate_enabled_config(self):
        if not self.enabled:
            return self

        if self.sensor_id is None:
            raise ValueError("temperature_control.sensor_id is required when enabled")
        if self.target_temperature_c is None:
            raise ValueError(
                "temperature_control.target_temperature_c is required when enabled"
            )
        return self

    @property
    def start_threshold_c(self) -> float | None:
        if self.target_temperature_c is None:
            return None
        return self.target_temperature_c - self.start_below_target_delta_c

    @property
    def stop_threshold_c(self) -> float | None:
        if self.target_temperature_c is None:
            return None
        return self.target_temperature_c + self.stop_above_target_delta_c


class HardwareSensorConfig(BaseModel):
    sensor_id: str
    type: SensorType
    address: str
    unit: str = "C"
    offset_c: float = 0.0

    @field_validator("sensor_id", "address")
    @classmethod
    def validate_non_empty_string(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("sensor_id and address must not be empty")
        return normalized

    @field_validator("unit")
    @classmethod
    def validate_unit(cls, value: str) -> str:
        normalized = value.strip()
        if normalized != "C":
            raise ValueError("Only Celsius sensors are supported in v1")
        return normalized


class SensorSnapshot(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    sensor_id: str
    sensor_type: SensorType
    value: float | None = None
    unit: str = "C"
    measured_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    status: SensorStatus = SensorStatus.OK
