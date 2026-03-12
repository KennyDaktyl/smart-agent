from typing import Any, Dict, List

from pydantic import BaseModel, Field


class HeartbeatPayload(BaseModel):
    uuid: str
    available_sensors: List[str] = Field(default_factory=list)
    sensor_snapshot: List[Dict[str, Any]] = Field(default_factory=list)
    devices: List[Dict[str, Any]]
