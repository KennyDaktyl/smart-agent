# app/infrastructure/backend/backend_adapter.py
import json
import logging
import socket
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Optional
from urllib.parse import quote, urlparse

import requests

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
        self.invalid_queue_path = Path(settings.LOG_DIR) / "invalid_backend_events.jsonl"
        try:
            self.queue_path.parent.mkdir(parents=True, exist_ok=True)
        except Exception:
            logging.warning("BackendAdapter: failed to prepare queue directory.")

        if self.base_url:
            logging.info("BackendAdapter: initialized | base_url=%s", self.base_url)
            self._log_backend_target_resolution()
        else:
            logging.warning(
                "BackendAdapter: disabled because BACKEND_URL is not configured."
            )

    def is_enabled(self) -> bool:
        return bool(self.base_url)

    class MissingDeviceUUIDError(ValueError):
        pass

    @staticmethod
    def _truncate_text(text: str, limit: int = 700) -> str:
        if len(text) <= limit:
            return text
        return f"{text[:limit]}...<truncated>"

    def _log_backend_target_resolution(self) -> None:
        try:
            parsed = urlparse(self.base_url or "")
            host = parsed.hostname
            if not host:
                logging.warning(
                    "BackendAdapter: could not parse backend host from base_url=%s",
                    self.base_url,
                )
                return

            scheme = (parsed.scheme or "").lower()
            port = parsed.port or (443 if scheme == "https" else 80)
            resolved = sorted(
                {
                    entry[4][0]
                    for entry in socket.getaddrinfo(
                        host,
                        port,
                        proto=socket.IPPROTO_TCP,
                    )
                }
            )
            logging.info(
                "BackendAdapter: backend DNS | host=%s port=%s resolved_ips=%s",
                host,
                port,
                resolved,
            )
        except Exception as exc:
            logging.warning("BackendAdapter: failed backend DNS resolution: %s", exc)

    def _events_url(self, device_uuid: str) -> str:
        normalized_uuid = device_uuid.strip()
        if not normalized_uuid:
            raise self.MissingDeviceUUIDError("device_uuid is required for agent event")
        encoded_uuid = quote(normalized_uuid, safe="")
        return f"{self.base_url}/device-events/agent/{encoded_uuid}"

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
    def _http_error_details(exc: requests.HTTPError) -> str:
        response = getattr(exc, "response", None)
        request = getattr(exc, "request", None)

        try:
            body = response.text.strip() if response is not None else ""
        except Exception:
            body = ""

        status = response.status_code if response is not None else "unknown"
        url = None
        if request is not None:
            url = getattr(request, "url", None)
        if not url and response is not None:
            url = getattr(response, "url", None)

        if body:
            return f"status={status} url={url} body={body}"
        return str(exc)

    def _prepare_request(self, payload: dict) -> tuple[str, dict]:
        normalized = self._enrich_identifiers_from_runtime(dict(payload))
        raw_device_uuid = normalized.get("device_uuid")
        device_uuid = (
            raw_device_uuid.strip()
            if isinstance(raw_device_uuid, str) and raw_device_uuid.strip()
            else None
        )
        if not device_uuid:
            raise self.MissingDeviceUUIDError(
                "device_uuid is required; old /agent endpoint without uuid is disabled"
            )

        request_payload = {
            key: value
            for key, value in normalized.items()
            if key not in {"device_uuid", "device_id", "device_number"}
        }
        return self._events_url(device_uuid), request_payload

    @staticmethod
    def _looks_like_valid_event_payload(payload: dict) -> bool:
        if not isinstance(payload, dict):
            return False
        if not payload.get("event_name"):
            return False
        if not payload.get("event_type"):
            return False
        return True

    def _store_invalid_queue_line(
        self,
        *,
        raw_line: str,
        reason: str,
        payload: dict | None = None,
    ) -> None:
        try:
            record = {
                "reason": reason,
                "raw_line": raw_line.rstrip("\n"),
                "payload": payload,
                "logged_at": datetime.now(timezone.utc).isoformat(),
            }
            with open(self.invalid_queue_path, "a") as f:
                f.write(json.dumps(record) + "\n")
        except Exception as exc:
            logging.error(
                "BackendAdapter: failed to persist invalid queue line: %s",
                exc,
            )

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

    def _post_payload(self, payload: dict) -> requests.Response:
        url, request_payload = self._prepare_request(payload)
        headers = self._headers()

        logging.info(
            "BackendAdapter: sending event | url=%s auth=%s payload=%s",
            url,
            "present" if "Authorization" in headers else "missing",
            request_payload,
        )

        response = requests.post(
            url,
            json=request_payload,
            headers=headers,
            timeout=5.0,
        )
        response_text = self._truncate_text(response.text or "")

        if response.status_code >= 400:
            logging.warning(
                "BackendAdapter: response error | status=%s url=%s body=%s",
                response.status_code,
                url,
                response_text,
            )
        else:
            logging.info(
                "BackendAdapter: response ok | status=%s url=%s body=%s",
                response.status_code,
                url,
                response_text,
            )

        return response

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
                stripped_line = line.strip()
                if not stripped_line:
                    continue

                payload = json.loads(stripped_line)
                if not self._looks_like_valid_event_payload(payload):
                    logging.error(
                        "BackendAdapter: dropping invalid queued payload: %s",
                        payload,
                    )
                    self._store_invalid_queue_line(
                        raw_line=line,
                        reason="missing event_name/event_type",
                        payload=payload,
                    )
                    continue
                resp = self._post_payload(payload)
                resp.raise_for_status()
                logging.info(f"BackendAdapter: flushed queued event {payload}")
            except json.JSONDecodeError as exc:
                logging.error(
                    "BackendAdapter: dropping malformed queued line. Error: %s",
                    exc,
                )
                self._store_invalid_queue_line(
                    raw_line=line,
                    reason=f"json decode error: {exc}",
                )
                continue
            except self.MissingDeviceUUIDError as exc:
                remaining.append(line)
                logging.warning(
                    "BackendAdapter: queued event missing device_uuid, "
                    "will keep queued. Error: %s",
                    exc,
                )
            except requests.HTTPError as exc:
                remaining.append(line)
                logging.warning(
                    "BackendAdapter: failed to flush queued event, "
                    "will keep queued. Error: %s",
                    self._http_error_details(exc),
                )
            except requests.RequestException as exc:
                remaining.append(line)
                logging.warning(
                    "BackendAdapter: failed to flush queued event due to request "
                    "error, will keep queued. Error: %s",
                    exc,
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
        except self.MissingDeviceUUIDError as exc:
            logging.warning(
                "BackendAdapter: immediate send skipped, missing device_uuid. "
                "Will keep queued. Error: %s",
                exc,
            )
            self._enqueue(payload)
        except requests.HTTPError as exc:
            logging.warning(
                "BackendAdapter: immediate send failed. Error: %s",
                self._http_error_details(exc),
            )
            self._enqueue(payload)
        except requests.RequestException as exc:
            logging.warning(
                "BackendAdapter: immediate send failed due to request error. "
                "Error: %s",
                exc,
            )
            self._enqueue(payload)
        except Exception as exc:
            logging.warning(
                "BackendAdapter: immediate send failed. Error: %s",
                exc,
            )
            self._enqueue(payload)


backend_adapter = BackendAdapter(settings.BACKEND_URL)
