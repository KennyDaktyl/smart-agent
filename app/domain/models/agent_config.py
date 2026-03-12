from enum import Enum
from typing import Dict, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

from app.domain.automation_rule import AutomationRuleGroup
from app.domain.models.device_dependency import DeviceDependencyRule
from app.domain.models.sensor import TemperatureControlConfig


class DeviceMode(str, Enum):
    MANUAL = "MANUAL"
    AUTO = "AUTO"
    SCHEDULE = "SCHEDULE"
    SCHEDULER = "SCHEDULER"


class DeviceConfig(BaseModel):
    device_id: int
    device_uuid: str
    device_number: int
    mode: DeviceMode
    rated_power: Optional[float] = None
    threshold_value: Optional[float] = None
    threshold_unit: Optional[str] = None
    auto_rule: Optional[AutomationRuleGroup] = None
    device_dependency_rule: Optional[DeviceDependencyRule] = None
    temperature_control: Optional[TemperatureControlConfig] = None
    desired_state: Optional[bool] = None

    @field_validator("device_number")
    @classmethod
    def validate_device_number(cls, value: int) -> int:
        if value < 1:
            raise ValueError("device_number must be >= 1")
        return value

    @field_validator("device_uuid")
    @classmethod
    def validate_device_uuid(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("device_uuid must not be empty")
        return normalized


class AgentConfig(BaseModel):
    config_version: int = 2
    microcontroller_uuid: str
    provider_uuid: str
    unit: Optional[str] = None
    provider_has_power_meter: bool = False
    provider_has_energy_storage: bool = False
    heartbeat_interval: int = 60
    sensor_poll_interval_sec: int = 5
    sensor_publish_interval_sec: int = 60
    sensor_change_threshold_c: float = 0.5
    device_max: int = 1
    available_sensors: list[str] = Field(default_factory=list)
    devices: Dict[int, DeviceConfig] = Field(default_factory=dict)

    @field_validator("device_max")
    @classmethod
    def validate_device_max(cls, value: int) -> int:
        if value < 1:
            raise ValueError("device_max must be >= 1")
        return value

    @field_validator("heartbeat_interval")
    @classmethod
    def validate_heartbeat_interval(cls, value: int) -> int:
        if value < 1:
            raise ValueError("heartbeat_interval must be >= 1")
        return value

    @field_validator("sensor_poll_interval_sec", "sensor_publish_interval_sec")
    @classmethod
    def validate_sensor_interval(cls, value: int) -> int:
        if value < 1:
            raise ValueError("sensor intervals must be >= 1")
        return value

    @field_validator("sensor_change_threshold_c")
    @classmethod
    def validate_sensor_change_threshold(cls, value: float) -> float:
        if value < 0:
            raise ValueError("sensor_change_threshold_c must be >= 0")
        return value

    @field_validator("provider_uuid")
    @classmethod
    def validate_provider_uuid(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("provider_uuid must not be empty")
        return normalized

    @field_validator("unit")
    @classmethod
    def validate_unit(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @field_validator("available_sensors", mode="before")
    @classmethod
    def validate_available_sensors(cls, value) -> list[str]:
        if value is None:
            return []
        if not isinstance(value, list):
            raise ValueError("available_sensors must be a list")

        normalized: list[str] = []
        seen: set[str] = set()

        for item in value:
            sensor = str(item).strip().lower()
            if not sensor:
                continue
            if sensor in seen:
                continue
            seen.add(sensor)
            normalized.append(sensor)

        return normalized

    @model_validator(mode="after")
    def validate_devices_mapping(self):
        seen_device_uuids: set[str] = set()
        for key, device in self.devices.items():
            if key != device.device_number:
                raise ValueError(
                    f"Device key ({key}) must match device_number ({device.device_number})"
                )
            if device.device_uuid in seen_device_uuids:
                raise ValueError(
                    f"Duplicate device_uuid detected: {device.device_uuid}"
                )
            seen_device_uuids.add(device.device_uuid)
        return self
