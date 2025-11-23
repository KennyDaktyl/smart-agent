import json
import logging

from app.application.event_service import event_service
from app.core.config import settings
from app.core.nats_client import nats_client
from app.domain.events.device_events import (DeviceCommandEvent, DeviceCreatedEvent,
                                             DeviceUpdatedEvent, EventType, PowerReadingEvent)

logger = logging.getLogger(__name__)


async def nats_event_handler(msg):
    try:
        raw = json.loads(msg.data.decode())
        event_type = raw.get("event_type")

        logger.info(f"Received raw event: {raw}")

        match event_type:
            case EventType.DEVICE_CREATED:
                event = DeviceCreatedEvent(**raw)

            case EventType.DEVICE_UPDATED:
                event = DeviceUpdatedEvent(**raw)

            case EventType.POWER_READING:
                event = PowerReadingEvent(**raw)

            case EventType.DEVICE_COMMAND:
                event = DeviceCommandEvent(**raw)

            case _:
                logger.error(f"Unknown event type: {event_type}")
                return

        await event_service.handle_event(event)

        await msg.ack()
        logger.info("JetStream ACK sent.")

        # Backend ACK
        ack_subject = f"raspberry.{settings.RASPBERRY_UUID}.events.ack"
        ack_payload = {"device_id": event.payload.device_id, "ok": True}

        await nats_client.publish_raw(ack_subject, ack_payload)
        logger.info(f"✔ Backend ACK sent: {ack_payload}")

    except Exception:
        logger.exception("Error while handling event")
