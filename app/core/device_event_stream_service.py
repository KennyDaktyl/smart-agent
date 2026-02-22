import logging
from datetime import datetime, timezone

from app.core.nats_client import nats_client
from app.core.nats_subjects import DeviceEvents, NatsSubjects
from app.domain.gpio.runtime_device import RuntimeDevice
from app.infrastructure.backend.backend_adapter import (
    DeviceEventName,
    DeviceEventType,
    DeviceState,
    DeviceTriggerReason,
    EventSource,
)

logger = logging.getLogger(__name__)

OUTGOING_DEVICE_EVENT_TYPE = "DEVICE_EVENT"


class DeviceEventStreamService:

    @staticmethod
    def _event_name(is_on: bool) -> DeviceEventName:
        if is_on:
            return DeviceEventName.DEVICE_ON
        return DeviceEventName.DEVICE_OFF

    @staticmethod
    def _device_state(is_on: bool) -> DeviceState:
        if is_on:
            return DeviceState.ON
        return DeviceState.OFF

    @staticmethod
    def _subject(device_uuid: str) -> str:
        return NatsSubjects.device_event(
            device_uuid,
            DeviceEvents.DEVICE_EVENT,
        )

    async def publish_state_change(
        self,
        *,
        device: RuntimeDevice,
        event_type: DeviceEventType,
        is_on: bool,
        trigger_reason: DeviceTriggerReason,
        measured_value: float | None = None,
        measured_unit: str = "kW",
        source: EventSource = EventSource.AGENT,
    ) -> bool:
        device_uuid = (device.device_uuid or "").strip()
        if not device_uuid:
            logger.warning(
                "Skipping device event publish: missing device_uuid for device_number=%s",
                device.device_number,
            )
            return False
        subject = self._subject(device_uuid)

        event_name = self._event_name(is_on)
        device_state = self._device_state(is_on)
        payload = {
            "id": None,
            "device_id": device.device_id,
            "event_type": event_type.value,
            "event_name": event_name.value,
            "device_state": device_state.value,
            "pin_state": is_on,
            "measured_value": measured_value,
            "measured_unit": measured_unit if measured_value is not None else None,
            "trigger_reason": trigger_reason.value,
            "source": source.value,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        event = {
            "event_type": OUTGOING_DEVICE_EVENT_TYPE,
            "subject": subject,
            "payload": payload,
        }

        try:
            logger.info(
                "Publishing device event | subject=%s payload=%s",
                subject,
                event,
            )
            await nats_client.js_publish(subject, event)
            return True
        except Exception:
            logger.exception(
                "Device event publish failed | device_id=%s device_number=%s",
                device.device_id,
                device.device_number,
            )
            return False


device_event_stream_service = DeviceEventStreamService()
