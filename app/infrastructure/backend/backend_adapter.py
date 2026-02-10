# app/infrastructure/backend/backend_adapter.py
import json
import logging
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Optional

import httpx

from app.core.config import settings

logging = logging.getLogger(__name__)


class DeviceEventType(str, Enum):
    STATE = "STATE"  # zmiana stanu ON/OFF
    MODE = "MODE"  # zmiana trybu MANUAL/AUTO
    HEARTBEAT = "HEARTBEAT"  # heartbeat ok / failed
    AUTO_TRIGGER = "AUTO_TRIGGER"
    SCHEDULER = "SCHEDULER"
    ERROR = "ERROR"


class DeviceEventName(str, Enum):
    # --- STATE ---
    DEVICE_ON = "DEVICE_ON"
    DEVICE_OFF = "DEVICE_OFF"
    SNAPSHOT = "SNAPSHOT"

    # --- MODE ---
    MANUAL_MODE_ON = "MANUAL_MODE_ON"
    AUTO_MODE_ON = "AUTO_MODE_ON"

    # --- AUTO ---
    AUTO_TRIGGER_ON = "AUTO_TRIGGER_ON"
    AUTO_TRIGGER_OFF = "AUTO_TRIGGER_OFF"
    AUTO_SKIPPED_NO_SCHEDULE = "AUTO_SKIPPED_NO_SCHEDULE"
    AUTO_SKIPPED_DISABLED = "AUTO_SKIPPED_DISABLED"

    # --- HEARTBEAT ---
    HEARTBEAT_OK = "HEARTBEAT_OK"
    HEARTBEAT_FAILED = "HEARTBEAT_FAILED"

    # --- ERROR ---
    PROVIDER_ERROR = "PROVIDER_ERROR"
    DEVICE_ERROR = "DEVICE_ERROR"


class BackendAdapter:

    def __init__(self, base_url: Optional[str]):
        self.base_url = base_url.rstrip("/") if base_url else None
        self.queue_path = Path(settings.LOG_DIR) / "pending_backend_events.jsonl"
        try:
            self.queue_path.parent.mkdir(parents=True, exist_ok=True)
        except Exception:
            logging.warning("BackendAdapter: failed to prepare queue directory.")

    def is_enabled(self) -> bool:
        return bool(self.base_url)

    def _headers(self) -> dict:
        """
        Authorization headers for machine-to-machine auth.
        """
        if not settings.BACKEND_AGENT_TOKEN:
            return {}

        return {
            "Authorization": f"Bearer {settings.BACKEND_AGENT_TOKEN}",
            "Content-Type": "application/json",
        }

    def _enqueue(self, payload: dict):
        try:
            with open(self.queue_path, "a") as f:
                f.write(json.dumps(payload) + "\n")
            logging.warning(f"BackendAdapter: queued event (offline): {payload}")
        except Exception as exc:
            logging.error(f"BackendAdapter: failed to enqueue offline event: {exc}")

    def _flush_queue(self):
        if not self.queue_path.exists():
            return

        try:
            with open(self.queue_path, "r") as f:
                lines = f.readlines()
        except Exception as exc:
            logging.error(f"BackendAdapter: failed to read offline queue: {exc}")
            return

        remaining = []
        for line in lines:
            try:
                payload = json.loads(line)
                resp = httpx.post(
                    f"{self.base_url}/device-events/agent",
                    json=payload,
                    headers=self._headers(),
                    timeout=5.0,
                )
                resp.raise_for_status()
                logging.info(f"BackendAdapter: flushed queued event {payload}")
            except Exception as exc:
                remaining.append(line)
                logging.warning(
                    f"BackendAdapter: failed to flush queued event, will keep queued. Error: {exc}"
                )

        if remaining:
            try:
                with open(self.queue_path, "w") as f:
                    f.writelines(remaining)
            except Exception as exc:
                logging.error(f"BackendAdapter: failed to rewrite offline queue: {exc}")
        else:
            try:
                self.queue_path.unlink(missing_ok=True)
            except Exception:
                pass

    def log_device_event(
        self,
        *,
        device_id: int,
        event_type: DeviceEventType = DeviceEventType.STATE,
        pin_state: bool | None,
        trigger_reason: str,
        power: float | None = None,
        source: str = "agent",
    ):
        if not self.is_enabled():
            return

        event_name = (
            DeviceEventName.DEVICE_ON
            if pin_state is True
            else (
                DeviceEventName.DEVICE_OFF
                if pin_state is False
                else DeviceEventName.SNAPSHOT
            )
        )

        payload = {
            "device_id": device_id,
            "event_type": event_type.value,
            "event_name": event_name.value,
            "device_state": (
                "ON" if pin_state else "OFF" if pin_state is not None else None
            ),
            "pin_state": pin_state,
            "measured_value": power,
            "measured_unit": "kW" if power is not None else None,
            "trigger_reason": trigger_reason,
            "source": source,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

        try:
            self._flush_queue()
            httpx.post(
                f"{self.base_url}/device-events",
                json=payload,
                headers=self._headers(),
                timeout=5.0,
            ).raise_for_status()
        except Exception:
            self._enqueue(payload)


backend_adapter = BackendAdapter(settings.BACKEND_URL)
