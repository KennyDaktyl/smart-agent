# app/interfaces/handlers/power_reading_handler.py
import json
import logging

from pydantic import ValidationError

from app.domain.events.enums import EventType
from app.domain.events.inverter_events import InverterProductionEvent
from app.application.power_reading_service import power_reading_service

logging = logging.getLogger(__name__)


async def inverter_production_handler(msg):
    try:
        raw = json.loads(msg.data.decode())

        logging.info(f"Inverter production event received: {raw}")

        try:
            event = InverterProductionEvent(**raw)
        except ValidationError as e:
            logging.error(f"Invalid inverter production event: {raw}")
            return

        if event.event_type != EventType.POWER_READING:
            logging.error(f"Unexpected event_type for inverter event: {event.event_type}")
            return

        await power_reading_service.handle_inverter_power(event)

    except Exception:
        logging.exception("Error handling inverter production update")
