from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class DeviceDependencyAction(str, Enum):
    NONE = "NONE"
    ON = "ON"
    OFF = "OFF"


class DeviceDependencyRule(BaseModel):
    target_device_id: int = Field(ge=1)
    target_device_number: int = Field(ge=1)
    when_source_on: DeviceDependencyAction = DeviceDependencyAction.NONE
    when_source_off: DeviceDependencyAction = DeviceDependencyAction.NONE
