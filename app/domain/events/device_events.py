from typing import List, Optional
from pydantic import BaseModel
from app.domain.events.enums import EventType


class BaseEvent(BaseModel):
    event_type: EventType
    event_id: str
    source: str
    entity_type: str
    entity_id: str
    timestamp: str
    data_version: str


class DeviceCreatedPayload(BaseModel):
    device_id: int
    device_number: int
    mode: str
    threshold_kw: Optional[float] = None


class DeviceCreatedEvent(BaseEvent):
    data: DeviceCreatedPayload


class DeviceUpdatedPayload(BaseModel):
    device_id: int
    mode: str
    threshold_kw: Optional[float] = None


class DeviceUpdatedEvent(BaseEvent):
    data: DeviceUpdatedPayload


class DeviceDeletePayload(BaseModel):
    device_id: int


class DeviceDeletedEvent(BaseEvent):
    data: DeviceDeletePayload


class PowerReadingPayload(BaseModel):
    inverter_id: int
    power_w: float
    device_ids: List[int]


class PowerReadingEvent(BaseEvent):
    data: PowerReadingPayload


class DeviceCommandPayload(BaseModel):
    device_id: int
    mode: Optional[str] = None
    command: str
    is_on: bool


class DeviceCommandEvent(BaseEvent):
    data: DeviceCommandPayload
