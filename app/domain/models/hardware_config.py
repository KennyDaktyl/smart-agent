from pydantic import BaseModel
from typing import Dict


class HardwareDeviceConfig(BaseModel):
    gpio: int
    active_low: bool


class HardwareConfig(BaseModel):
    config_version: int = 2
    devices: Dict[int, HardwareDeviceConfig]
