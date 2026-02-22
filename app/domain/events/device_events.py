from typing import Any, Dict, Optional

from pydantic import AliasChoices, BaseModel, Field, field_validator

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
    device_uuid: str
    device_number: int
    mode: str
    rated_power: Optional[float] = None
    threshold_value: Optional[float] = None
    is_on: bool = Field(
        default=False,
        validation_alias=AliasChoices("is_on", "manual_state", "desired_state"),
    )

    @field_validator("device_uuid")
    @classmethod
    def validate_device_uuid(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("device_uuid must not be empty")
        return normalized

    @field_validator("is_on", mode="before")
    @classmethod
    def normalize_is_on(cls, value: Any) -> bool:
        if value is None:
            return False
        return value


class DeviceCreatedEvent(BaseEvent):
    data: DeviceCreatedPayload


class DeviceUpdatedPayload(BaseModel):
    device_id: int
    device_uuid: Optional[str] = None
    device_number: int
    mode: str
    rated_power: Optional[float] = None
    threshold_value: Optional[float] = Field(
        default=None,
        validation_alias=AliasChoices("threshold_value", "threshold_kw"),
    )

    @field_validator("device_uuid")
    @classmethod
    def validate_device_uuid(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        normalized = value.strip()
        if not normalized:
            raise ValueError("device_uuid must not be empty")
        return normalized


class DeviceUpdatedEvent(BaseEvent):
    data: DeviceUpdatedPayload


class DeviceDeletePayload(BaseModel):
    device_id: int
    device_number: int


class DeviceDeletedEvent(BaseEvent):
    data: DeviceDeletePayload


class PowerReadingPayload(BaseModel):
    value: Optional[float] = Field(
        default=None,
        validation_alias=AliasChoices("value", "power_w", "active_power"),
    )
    unit: Optional[str] = None
    measured_at: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class PowerReadingEvent(BaseEvent):
    data: PowerReadingPayload


class DeviceCommandPayload(BaseModel):
    device_id: int
    device_number: int
    mode: str
    is_on: bool


class DeviceCommandEvent(BaseEvent):
    data: DeviceCommandPayload


class ProviderUpdatedPayload(BaseModel):
    provider_uuid: str = Field(
        validation_alias=AliasChoices("provider_uuid", "new_provider_uuid")
    )

    @field_validator("provider_uuid")
    @classmethod
    def validate_provider_uuid(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("provider_uuid must not be empty")
        return normalized


class ProviderUpdatedEvent(BaseEvent):
    data: ProviderUpdatedPayload
