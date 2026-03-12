from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from pydantic import BaseModel, Field, field_validator


class SchedulerPolicyType(str, Enum):
    TEMPERATURE_HYSTERESIS = "TEMPERATURE_HYSTERESIS"


class SchedulerPolicyEndBehavior(str, Enum):
    KEEP_CURRENT_STATE = "KEEP_CURRENT_STATE"
    FORCE_OFF = "FORCE_OFF"


class SchedulerControlPolicy(BaseModel):
    policy_type: SchedulerPolicyType = SchedulerPolicyType.TEMPERATURE_HYSTERESIS
    sensor_id: str = Field(min_length=1, max_length=128)
    target_temperature_c: float
    stop_above_target_delta_c: float = Field(default=0.0, ge=0)
    start_below_target_delta_c: float = Field(default=10.0, ge=0)
    heat_up_on_activate: bool = True
    end_behavior: SchedulerPolicyEndBehavior = (
        SchedulerPolicyEndBehavior.FORCE_OFF
    )

    @field_validator("sensor_id")
    @classmethod
    def normalize_sensor_id(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("sensor_id must not be empty")
        return normalized

    @property
    def start_threshold_c(self) -> float:
        return self.target_temperature_c - self.start_below_target_delta_c

    @property
    def stop_threshold_c(self) -> float:
        return self.target_temperature_c + self.stop_above_target_delta_c


class SchedulerTemperaturePhase(str, Enum):
    HEAT_UP = "HEAT_UP"
    HOLD = "HOLD"


@dataclass
class ActiveSchedulerPolicy:
    policy: SchedulerControlPolicy
    phase: SchedulerTemperaturePhase
