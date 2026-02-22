# app/infrastructure/backend/backend_adapter.py
import json
import logging
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Optional
from urllib.parse import quote

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


class DeviceTriggerReason(str, Enum):
    DEVICE_COMMAND = "DEVICE_COMMAND"
    AUTO_TRIGGER = "AUTO_TRIGGER"
    POWER_MISSING = "POWER_MISSING"
    STATE_CHANGE_FAILED = "STATE_CHANGE_FAILED"
    CONFIG_SYNC_FAILED = "CONFIG_SYNC_FAILED"
    CONFIG_APPLY = "CONFIG_APPLY"


class DeviceState(str, Enum):
    ON = "ON"
    OFF = "OFF"


class EventSource(str, Enum):
    AGENT = "agent"


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

    def _events_url(self, device_uuid: str | None = None) -> str:
        normalized_uuid = (device_uuid or "").strip()
        if normalized_uuid:
            encoded_uuid = quote(normalized_uuid, safe="")
            return f"{self.base_url}/device-events/agent/{encoded_uuid}"
        return f"{self.base_url}/device-events/agent"

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

    @staticmethod
    def _http_error_details(exc: httpx.HTTPStatusError) -> str:
        try:
            body = exc.response.text.strip()
        except Exception:
            body = ""

        if body:
            return (
                f"status={exc.response.status_code} url={exc.request.url} "
                f"body={body}"
            )
        return str(exc)

    def _prepare_request(self, payload: dict) -> tuple[str, dict]:
        raw_device_uuid = payload.get("device_uuid")
        device_uuid = (
            raw_device_uuid.strip()
            if isinstance(raw_device_uuid, str) and raw_device_uuid.strip()
            else None
        )

        if device_uuid:
            request_payload = {
                key: value
                for key, value in payload.items()
                if key not in {"device_uuid", "device_id", "device_number"}
            }
            return self._events_url(device_uuid), request_payload

        request_payload = {
            key: value for key, value in payload.items() if key != "device_uuid"
        }
        if request_payload.get("device_id") is not None:
            request_payload.pop("device_number", None)
        return self._events_url(), request_payload

    @staticmethod
    def _looks_like_valid_event_payload(payload: dict) -> bool:
        if not isinstance(payload, dict):
            return False
        if not payload.get("event_name"):
            return False
        if not payload.get("event_type"):
            return False
        return True

    @staticmethod
    def _enrich_identifiers_from_runtime(payload: dict) -> dict:
        if not isinstance(payload, dict):
            return payload

        if payload.get("device_id") is not None and payload.get("device_uuid"):
            return payload

        device_number = payload.get("device_number")
        if device_number is None:
            return payload

        try:
            device_number_int = int(device_number)
        except (TypeError, ValueError):
            return payload

        try:
            from app.infrastructure.gpio.gpio_manager import gpio_manager

            runtime_device = gpio_manager.get_by_number(device_number_int)
        except Exception:
            runtime_device = None

        if not runtime_device:
            return payload

        if payload.get("device_id") is None:
            payload["device_id"] = runtime_device.device_id
        if not payload.get("device_uuid"):
            payload["device_uuid"] = runtime_device.device_uuid
        return payload

    def _request_candidates(self, payload: dict) -> list[tuple[str, dict]]:
        normalized = self._enrich_identifiers_from_runtime(dict(payload))
        url, request_payload = self._prepare_request(normalized)

        candidates: list[tuple[str, dict]] = [(url, request_payload)]

        if "/device-events/agent/" in url:
            fallback_payload = {
                key: value for key, value in normalized.items() if key != "device_uuid"
            }
            if fallback_payload.get("device_id") is not None:
                fallback_payload.pop("device_number", None)
            candidates.append((self._events_url(), fallback_payload))

        return candidates

    def _post_payload(self, payload: dict) -> httpx.Response:
        candidates = self._request_candidates(payload)
        last_response: httpx.Response | None = None

        for idx, (url, request_payload) in enumerate(candidates):
            response = httpx.post(
                url,
                json=request_payload,
                headers=self._headers(),
                timeout=5.0,
            )
            last_response = response

            should_try_fallback = (
                response.status_code == 404 and idx < len(candidates) - 1
            )
            if should_try_fallback:
                logging.warning(
                    "BackendAdapter: endpoint not found, retrying with fallback "
                    "endpoint. status=%s url=%s",
                    response.status_code,
                    url,
                )
                continue

            return response

        if last_response is None:
            raise RuntimeError("BackendAdapter: no request candidate generated")
        return last_response

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
                if not self._looks_like_valid_event_payload(payload):
                    logging.error(
                        "BackendAdapter: dropping invalid queued payload: %s",
                        payload,
                    )
                    continue
                resp = self._post_payload(payload)
                resp.raise_for_status()
                logging.info(f"BackendAdapter: flushed queued event {payload}")
            except httpx.HTTPStatusError as exc:
                remaining.append(line)
                logging.warning(
                    "BackendAdapter: failed to flush queued event, "
                    "will keep queued. Error: %s",
                    self._http_error_details(exc),
                )
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
        device_uuid: str | None = None,
        device_id: int | None = None,
        device_number: int,
        event_type: DeviceEventType = DeviceEventType.STATE,
        is_on: bool | None,
        trigger_reason: DeviceTriggerReason | str,
        power: float | None = None,
        source: EventSource | str = EventSource.AGENT,
    ):
        if not self.is_enabled():
            return

        event_name = (
            DeviceEventName.DEVICE_ON
            if is_on is True
            else (
                DeviceEventName.DEVICE_OFF
                if is_on is False
                else DeviceEventName.SNAPSHOT
            )
        )

        trigger_reason_value = (
            trigger_reason.value
            if isinstance(trigger_reason, DeviceTriggerReason)
            else trigger_reason
        )
        source_value = source.value if isinstance(source, EventSource) else source
        device_state = (
            DeviceState.ON.value
            if is_on is True
            else DeviceState.OFF.value if is_on is False else None
        )

        payload = {
            "device_uuid": device_uuid,
            "device_id": device_id,
            "device_number": device_number,
            "event_type": event_type.value,
            "event_name": event_name.value,
            "device_state": device_state,
            "pin_state": is_on,
            "is_on": is_on,
            "measured_value": power,
            "measured_unit": "kW" if power is not None else None,
            "trigger_reason": trigger_reason_value,
            "source": source_value,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

        try:
            self._flush_queue()
            resp = self._post_payload(payload)
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            logging.warning(
                "BackendAdapter: immediate send failed. Error: %s",
                self._http_error_details(exc),
            )
            self._enqueue(payload)
        except Exception as exc:
            logging.warning(
                "BackendAdapter: immediate send failed. Error: %s",
                exc,
            )
            self._enqueue(payload)


backend_adapter = BackendAdapter(settings.BACKEND_URL)
