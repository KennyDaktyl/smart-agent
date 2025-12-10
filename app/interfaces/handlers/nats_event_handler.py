# app/interfaces/handlers/nats_event_handler.py
import json
import logging

from app.application.event_service import event_service
from app.core.config import settings
from app.core.nats_client import nats_client
from app.domain.events.device_events import (DeviceCommandEvent, DeviceCreatedEvent, DeviceDeletedEvent,
                                             DeviceUpdatedEvent, EventType, PowerReadingEvent)

logging = logging.getLogger(__name__)


async def nats_event_handler(msg):
    try:
        raw = json.loads(msg.data.decode())
        event_type = raw.get("event_type")

        logging.info(f"Received raw event: {raw}")

        match event_type:
            case EventType.DEVICE_CREATED:
                event = DeviceCreatedEvent(**raw)

            case EventType.DEVICE_UPDATED:
                event = DeviceUpdatedEvent(**raw)
                
            case EventType.DEVICE_DELETED:
                event = DeviceDeletedEvent(**raw)
                
            case EventType.POWER_READING:
                event = PowerReadingEvent(**raw)

            case EventType.DEVICE_COMMAND:
                event = DeviceCommandEvent(**raw)

            case _:
                logging.error(f"Unknown event type: {event_type}")
                return

        ok = False
        try:
            result = await event_service.handle_event(event)
            ok = bool(result) or result is None  # treat None as success for backward compatibility
        except Exception:
            logging.exception("Error while handling event")
            ok = False

        await msg.ack()
        logging.info("JetStream ACK sent.")

        # Backend ACK
        ack_subject = f"device_communication.raspberry.{settings.RASPBERRY_UUID}.events.ack"
        payload_dict = event.payload.model_dump()

        device_id = payload_dict.get("device_id")
        manual_state = payload_dict.get("is_on") if "is_on" in payload_dict else payload_dict.get("manual_state")

        # Format przyjazny backendowi:
        #  - top-level device_id
        #  - top-level ok (dla .get("ok"))
        #  - opcjonalny manual_state (alias is_on)
        #  - wewnętrzny ack dla zgodności wstecznej
        ack_payload = {
            "device_id": device_id,
            "ok": ok,
            **({"manual_state": manual_state} if manual_state is not None else {}),
            "ack": {
                "device_id": device_id,
                "ok": ok,
            },
        }

        await nats_client.publish_raw(ack_subject, ack_payload)
        logging.info(f"✔ Backend ACK subject={ack_subject} | sent: {ack_payload}")

    except Exception:
        logging.exception("Unhandled error while processing NATS event")
