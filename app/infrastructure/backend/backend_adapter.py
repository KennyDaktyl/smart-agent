# app/infrastructure/backend/backend_adapter.py
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


class BackendAdapter:

    def __init__(self, base_url: Optional[str]):
        self.base_url = base_url.rstrip("/") if base_url else None
        self.queue_path = Path(settings.LOG_DIR) / "pending_backend_events.jsonl"
        try:
            self.queue_path.parent.mkdir(parents=True, exist_ok=True)
        except Exception:
            logger.warning("BackendAdapter: failed to prepare queue directory.")

    def is_enabled(self) -> bool:
        return bool(self.base_url)

    def _enqueue(self, payload: dict):
        try:
            with open(self.queue_path, "a") as f:
                f.write(json.dumps(payload) + "\n")
            logger.warning(f"BackendAdapter: queued event (offline): {payload}")
        except Exception as exc:
            logger.error(f"BackendAdapter: failed to enqueue offline event: {exc}")

    def _flush_queue(self):
        if not self.queue_path.exists():
            return

        try:
            with open(self.queue_path, "r") as f:
                lines = f.readlines()
        except Exception as exc:
            logger.error(f"BackendAdapter: failed to read offline queue: {exc}")
            return

        remaining = []
        for line in lines:
            try:
                payload = json.loads(line)
                resp = httpx.post(f"{self.base_url}/device-events/", json=payload, timeout=5.0)
                resp.raise_for_status()
                logger.info(f"BackendAdapter: flushed queued event {payload}")
            except Exception as exc:
                remaining.append(line)
                logger.warning(f"BackendAdapter: failed to flush queued event, will keep queued. Error: {exc}")

        if remaining:
            try:
                with open(self.queue_path, "w") as f:
                    f.writelines(remaining)
            except Exception as exc:
                logger.error(f"BackendAdapter: failed to rewrite offline queue: {exc}")
        else:
            try:
                self.queue_path.unlink(missing_ok=True)
            except Exception:
                pass

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
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        if power_kw is not None:
            payload["power_kw"] = power_kw

        try:
            self._flush_queue()
            resp = httpx.post(url, json=payload, timeout=5.0)
            resp.raise_for_status()
            logger.info(f"BackendAdapter: sent device event {payload}")
        except httpx.HTTPStatusError as exc:
            logger.error(f"BackendAdapter: backend responded with error: {exc.response.status_code} {exc.response.text}")
            self._enqueue(payload)
        except httpx.RequestError as exc:
            logger.error(f"BackendAdapter: request error while sending device event: {exc}")
            self._enqueue(payload)


backend_adapter = BackendAdapter(settings.BACKEND_URL)
