from pydantic import BaseModel
from typing import Dict, Optional


class HardwareDeviceConfig(BaseModel):
    gpio: int
    active_low: Optional[bool] = None


class HardwareConfig(BaseModel):
    config_version: int = 2
    devices: Dict[int, HardwareDeviceConfig]
