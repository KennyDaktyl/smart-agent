from typing import Optional

from pydantic import BaseModel

from app.domain.device.enums import DeviceMode


class Device(BaseModel):

    id: int
    name: str
    user_id: int
    device_number: int
    mode: DeviceMode = DeviceMode.MANUAL
    power_threshold_w: Optional[float] = None
    inverter_id: Optional[int] = None
    raspberry_uuid: Optional[str] = None

    class Config:
        from_attributes = True
