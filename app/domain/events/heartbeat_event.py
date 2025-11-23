from typing import Any, Dict, List

from pydantic import BaseModel


class HeartbeatPayload(BaseModel):
    uuid: str
    devices: List[Dict[str, Any]]
