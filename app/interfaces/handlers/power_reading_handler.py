import json
import logging

from pydantic import ValidationError

from app.domain.events.inverter_events import InverterProductionEvent
from app.application.power_reading_service import power_reading_service

logger = logging.getLogger(__name__)


async def inverter_production_handler(msg):
    try:
        raw = json.loads(msg.data.decode())

        logger.info(f"Inverter production event received: {raw}")

        try:
            event = InverterProductionEvent(**raw)
        except ValidationError as e:
            logger.error(f"Invalid inverter production event: {raw}")
            return

        await power_reading_service.handle_inverter_power(event)

    except Exception:
        logger.exception("Error handling inverter production update")
