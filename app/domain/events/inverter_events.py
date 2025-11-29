from datetime import datetime
from typing import Optional
from pydantic import BaseModel


class InverterProductionEvent(BaseModel):
    inverter_id: int
    serial_number: str
    active_power: Optional[float] = None
    status: str
    timestamp: datetime
    error_message: Optional[str] = None
