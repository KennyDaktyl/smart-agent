from typing import List, Optional

from pydantic import BaseModel

from app.domain.events.enums import EventType


class BaseEvent(BaseModel):
    event_type: EventType


class DeviceCreatedPayload(BaseModel):
    device_id: int
    device_number: int
    mode: str
    threshold_kw: Optional[float] = None


class DeviceCreatedEvent(BaseEvent):
    payload: DeviceCreatedPayload


class DeviceUpdatedPayload(BaseModel):
    device_id: int
    mode: str
    threshold_kw: Optional[float] = None


class DeviceUpdatedEvent(BaseEvent):
    payload: DeviceUpdatedPayload


class DeviceDeletePayload(BaseModel):
    device_id: int

class DeviceDeletedEvent(BaseModel):
    event_type: str
    payload: DeviceDeletePayload


class PowerReadingPayload(BaseModel):
    inverter_id: int
    power_w: float
    device_ids: List[int]


class PowerReadingEvent(BaseEvent):
    payload: PowerReadingPayload


class DeviceCommandPayload(BaseModel):
    device_id: int
    command: str
    is_on: bool


class DeviceCommandEvent(BaseEvent):
    payload: DeviceCommandPayload
