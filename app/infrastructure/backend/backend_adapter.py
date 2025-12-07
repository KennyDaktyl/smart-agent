# app/infrastructure/backend/backend_adapter.py
import logging
from datetime import datetime, timezone
from typing import Optional

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


class BackendAdapter:

    def __init__(self, base_url: Optional[str]):
        self.base_url = base_url.rstrip("/") if base_url else None

    def is_enabled(self) -> bool:
        return bool(self.base_url)

    def log_device_event(self, device_id: int, pin_state: bool, trigger_reason: str, power_kw: Optional[float] = None):
        """Send device state change to backend; non-blocking for agent stability."""
        if not self.is_enabled():
            logger.debug("BackendAdapter disabled (BACKEND_URL not set). Skipping device event.")
            return

        url = f"{self.base_url}/device-events/"
        payload = {
            "device_id": device_id,
            "pin_state": pin_state,
            "trigger_reason": trigger_reason,
            "power_kw": power_kw,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        try:
            resp = httpx.post(url, json=payload, timeout=5.0)
            resp.raise_for_status()
            logger.info(f"BackendAdapter: sent device event {payload}")
        except httpx.HTTPStatusError as exc:
            logger.error(f"BackendAdapter: backend responded with error: {exc.response.status_code} {exc.response.text}")
        except httpx.RequestError as exc:
            logger.error(f"BackendAdapter: request error while sending device event: {exc}")


backend_adapter = BackendAdapter(settings.BACKEND_URL)
