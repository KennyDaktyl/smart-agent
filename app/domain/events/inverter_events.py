from typing import Optional, Dict, Any
from pydantic import BaseModel
from app.domain.events.enums import EventType


# =====================================================
# BASE EVENT – wspólna koperta
# =====================================================


class BaseEvent(BaseModel):
    event_type: EventType
    event_id: str
    source: str
    entity_type: str
    entity_id: str
    timestamp: str
    data_version: str


class InverterProductionPayload(BaseModel):
    value: float
    unit: str
    measured_at: str
    metadata: Optional[Dict[str, Any]] = None


class InverterProductionEvent(BaseEvent):
    data: InverterProductionPayload
