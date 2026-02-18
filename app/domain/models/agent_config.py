from enum import Enum
from typing import Dict, Optional

from pydantic import BaseModel, Field, field_validator


class DeviceMode(str, Enum):
    MANUAL = "MANUAL"
    AUTO = "AUTO"
    SCHEDULE = "SCHEDULE"
    SCHEDULER = "SCHEDULER"


class DeviceConfig(BaseModel):
    device_id: int
    mode: DeviceMode
    rated_power: Optional[float] = None
    power_threshold: Optional[float] = None
    desired_state: bool = False


class HeartbeatConfig(BaseModel):
    enabled: bool = True
    interval: int = 5


class AgentConfig(BaseModel):
    config_version: int = 2
    microcontroller_uuid: str
    provider_uuid: str
    active_low: bool = False
    heartbeat: HeartbeatConfig = Field(default_factory=HeartbeatConfig)
    device_max: int = 1
    devices: Dict[int, DeviceConfig] = Field(default_factory=dict)

    @field_validator("device_max")
    @classmethod
    def validate_device_max(cls, value: int) -> int:
        if value < 1:
            raise ValueError("device_max must be >= 1")
        return value
