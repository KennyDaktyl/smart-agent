from dataclasses import dataclass
from typing import Optional

from app.domain.models.agent_config import DeviceMode


@dataclass
class RuntimeDevice:
    device_number: int
    device_id: int
    gpio: int
    active_low: bool
    mode: DeviceMode
    rated_power: Optional[float] = None
    power_threshold: Optional[float] = None
    desired_state: bool = False
