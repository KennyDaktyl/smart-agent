from typing import Optional

from pydantic import BaseModel

from app.domain.device.enums import DeviceMode


class GPIODeviceConfig(BaseModel):
    device_id: int
    pin_number: int
    mode: DeviceMode
    power_threshold_kw: Optional[float] = None
