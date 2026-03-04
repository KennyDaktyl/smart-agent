# app/interfaces/handlers/power_reading_handler.py
import json
import logging

from pydantic import ValidationError

from app.application.event_service import event_service
from app.domain.events.device_events import PowerReadingEvent
from app.domain.events.enums import EventType

logging = logging.getLogger(__name__)


async def inverter_production_handler(msg):
    try:
        raw = json.loads(msg.data.decode())
        logging.info(f"Inverter production event received: {raw}")

        event = PowerReadingEvent(**raw)

        if event.event_type != EventType.CURRENT_ENERGY:
            logging.warning(f"Ignoring inverter event type={event.event_type}")
            return

        await event_service.handle_event(event)

    except ValidationError as e:
        logging.error(
            "Invalid inverter production event schema",
            exc_info=e,
        )

    except Exception:
        logging.exception("Error handling inverter production update")
