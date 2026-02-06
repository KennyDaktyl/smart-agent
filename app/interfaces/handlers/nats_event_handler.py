import json
import logging

from app.application.event_service import event_service
from app.core.nats_client import nats_client
from app.domain.events.device_events import (
    DeviceCommandEvent,
    DeviceCreatedEvent,
    DeviceDeletedEvent,
    DeviceUpdatedEvent,
    EventType,
    PowerReadingEvent,
)

logger = logging.getLogger(__name__)


async def nats_event_handler(msg):
    try:
        raw = json.loads(msg.data.decode())
        event_type = raw.get("event_type")

        logger.info("📩 EVENT RECEIVED | subject=%s payload=%s", msg.subject, raw)

        ack_subject = raw.get("ack_subject")
        if not ack_subject:
            logger.error("❌ Missing ack_subject in event payload")
            return

        # -------------------------------------------------
        # Parse event
        # -------------------------------------------------
        match event_type:
            case EventType.DEVICE_CREATED:
                event = DeviceCreatedEvent(**raw)
            case EventType.DEVICE_UPDATED:
                event = DeviceUpdatedEvent(**raw)
            case EventType.DEVICE_DELETED:
                event = DeviceDeletedEvent(**raw)
            case EventType.DEVICE_COMMAND:
                event = DeviceCommandEvent(**raw)
            case EventType.CURRENT_ENERGY:
                event = PowerReadingEvent(**raw)
            case _:
                logger.error("❌ Unknown event type: %s", event_type)
                await _send_ack(ack_subject, raw.get("device_id"), ok=False)
                return

        # -------------------------------------------------
        # Execute event
        # -------------------------------------------------
        ok = False
        try:
            result = await event_service.handle_event(event)
            ok = bool(result) or result is None
        except Exception:
            logger.exception("❌ Error while handling event")
            ok = False

        # -------------------------------------------------
        # Build ACK payload (⬅️ DOSTOSOWANE DO BACKENDU)
        # -------------------------------------------------
        payload = event.data.model_dump()
        device_id = payload.get("device_id")
        manual_state = payload.get("is_on") or payload.get("manual_state")

        ack_payload = {
            "data": {
                "device_id": device_id,
                "ok": ok,
                **({"manual_state": manual_state} if manual_state is not None else {}),
            }
        }

        # -------------------------------------------------
        # SEND ACK (Core NATS)
        # -------------------------------------------------
        await nats_client.publish_raw(
            ack_subject,
            ack_payload,
        )

        logger.info("✅ ACK SENT | subject=%s payload=%s", ack_subject, ack_payload)

    except Exception:
        logger.exception("🔥 Unhandled error while processing NATS event")


async def _send_ack(ack_subject: str, device_id: int | None, ok: bool):
    await nats_client.publish_raw(
        ack_subject,
        {
            "data": {
                "device_id": device_id,
                "ok": ok,
            }
        },
    )
