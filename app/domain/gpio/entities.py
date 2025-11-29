# app/domain/gpio/entities.py
from typing import Optional

from pydantic import BaseModel

from app.domain.device.enums import DeviceMode


class GPIODevice(BaseModel):

    device_id: int
    device_number: int
    pin_number: int
    mode: DeviceMode
    power_threshold_kw: Optional[float]
    is_on: Optional[bool] = None
