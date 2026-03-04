from enum import Enum
from typing import Dict, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


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
    heartbeat_interval: int = 60
    device_max: int = 1
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

    @field_validator("provider_uuid")
    @classmethod
    def validate_provider_uuid(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("provider_uuid must not be empty")
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
