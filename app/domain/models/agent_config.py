from pydantic import BaseModel
from typing import Dict, Optional
from enum import Enum


class DeviceMode(str, Enum):
    MANUAL = "MANUAL"
    AUTO = "AUTO"
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
    config_version: int = 1
    microcontroller_uuid: str
    provider_uuid: str
    heartbeat: HeartbeatConfig
    devices: Dict[int, DeviceConfig]
