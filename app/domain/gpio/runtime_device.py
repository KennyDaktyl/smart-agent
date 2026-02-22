from dataclasses import dataclass
from typing import Optional

from app.domain.models.agent_config import DeviceMode


@dataclass
class RuntimeDevice:
    device_id: int
    device_uuid: str
    device_number: int
    gpio: int
    active_low: bool
    mode: DeviceMode
    rated_power: Optional[float] = None
    threshold_value: Optional[float] = None
    desired_state: Optional[bool] = None
