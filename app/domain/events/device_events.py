from typing import Any, Dict, Optional

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator

from app.domain.automation_rule import AutomationRuleGroup
from app.domain.events.enums import EventType, MicrocontrollerCommandType
from app.domain.models.device_dependency import DeviceDependencyRule
from app.domain.models.scheduler_policy import SchedulerControlPolicy
from app.domain.models.sensor import TemperatureControlConfig


class BaseEvent(BaseModel):
    model_config = ConfigDict(extra="ignore")

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
    threshold_unit: Optional[str] = None
    auto_rule: Optional[AutomationRuleGroup] = None
    device_dependency_rule: Optional[DeviceDependencyRule] = None
    temperature_control: Optional[TemperatureControlConfig] = None
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
    threshold_unit: Optional[str] = None
    auto_rule: Optional[AutomationRuleGroup] = None
    device_dependency_rule: Optional[DeviceDependencyRule] = None
    temperature_control: Optional[TemperatureControlConfig] = None

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


class MetricSnapshotPayload(BaseModel):
    model_config = ConfigDict(extra="ignore")

    value: Optional[float] = None
    unit: Optional[str] = None


class PowerReadingPayload(BaseModel):
    model_config = ConfigDict(extra="ignore")

    value: Optional[float] = Field(
        default=None,
        validation_alias=AliasChoices("value", "power_w", "active_power"),
    )
    unit: Optional[str] = None
    measured_at: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    extra_metrics: Optional[list[Dict[str, Any]]] = None
    battery_soc: Optional[MetricSnapshotPayload] = None
    grid_power: Optional[MetricSnapshotPayload] = None


class PowerReadingEvent(BaseEvent):
    data: PowerReadingPayload


class DeviceCommandPayload(BaseModel):
    command_id: Optional[str] = None
    device_id: int
    device_number: int
    mode: str
    command: str = "SET_STATE"
    is_on: bool
    scheduler_policy_enabled: Optional[bool] = None
    scheduler_policy: Optional[SchedulerControlPolicy] = None
    device_dependency_rule: Optional[DeviceDependencyRule] = None


class DeviceCommandEvent(BaseEvent):
    data: DeviceCommandPayload


class MicrocontrollerCommandPayload(BaseModel):
    command_id: Optional[str] = None
    command: MicrocontrollerCommandType
    config_json: Optional[Dict[str, Any]] = None
    hardware_config_json: Optional[Dict[str, Any]] = None
    env_file_content: Optional[str] = None


class MicrocontrollerCommandEvent(BaseEvent):
    data: MicrocontrollerCommandPayload


class ProviderUpdatedPayload(BaseModel):
    provider_uuid: str = Field(
        validation_alias=AliasChoices("provider_uuid", "new_provider_uuid")
    )
    unit: Optional[str] = None
    has_power_meter: Optional[bool] = None
    has_energy_storage: Optional[bool] = None

    @field_validator("provider_uuid")
    @classmethod
    def validate_provider_uuid(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("provider_uuid must not be empty")
        return normalized

    @field_validator("unit")
    @classmethod
    def validate_unit(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None


class ProviderUpdatedEvent(BaseEvent):
    data: ProviderUpdatedPayload
