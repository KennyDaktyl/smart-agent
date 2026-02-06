import json
import logging

from app.application.event_service import event_service
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

        logger.info("Received raw event: %s", raw)

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
                logger.error("Unknown event type: %s", event_type)
                await msg.ack()
                return

        # -------------------------------------------------
        # Execute event
        # -------------------------------------------------
        ok = False
        try:
            result = await event_service.handle_event(event)
            ok = bool(result) or result is None
        except Exception:
            logger.exception("Error while handling event")
            ok = False

        # -------------------------------------------------
        # JetStream ACK (delivery-level)
        # -------------------------------------------------
        await msg.ack()
        logger.info("JetStream ACK sent.")

        # -------------------------------------------------
        # Extract ACK data (🔥 TO BYŁ BRAKUJĄCY KROK)
        # -------------------------------------------------
        payload = event.data.model_dump()

        device_id = payload.get("device_id")
        manual_state = payload.get("is_on") or payload.get("manual_state")

        # -------------------------------------------------
        # Backend REPLY (command-level ACK)
        # -------------------------------------------------
        ack_payload = {
            "device_id": device_id,
            "ok": ok,
            **({"manual_state": manual_state} if manual_state is not None else {}),
            "ack": {
                "device_id": device_id,
                "ok": ok,
            },
        }

        await msg.respond(json.dumps(ack_payload).encode())
        logger.info("✔ Backend REPLY sent | %s", ack_payload)

    except Exception:
        logger.exception("Unhandled error while processing NATS event")
