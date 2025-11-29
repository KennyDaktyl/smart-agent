from typing import Optional

from pydantic import BaseModel

from app.domain.events.enums import EventType


class DeviceCreatedEvent(BaseModel):
    event: EventType = EventType.DEVICE_CREATED
    device_id: int
    gpio_pin: int
    mode: str
    threshold_kw: Optional[float]


class DeviceUpdatedEvent(BaseModel):
    event: EventType = EventType.DEVICE_UPDATED
    device_id: int
    mode: str
    threshold_kw: Optional[float]


class PowerReadingEvent(BaseModel):
    event: EventType = EventType.POWER_READING
    inverter_id: int
    power_w: float
    device_ids: list[int]
