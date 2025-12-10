import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List

from app.core.config import settings
from app.core.nats_client import nats_client
from app.domain.events.enums import EventType
from app.infrastructure.gpio.gpio_manager import gpio_manager

logging = logging.getLogger(__name__)


async def send_heartbeat() -> None:

    await asyncio.sleep(1)

    subject = f"device_communication.raspberry.{settings.RASPBERRY_UUID}.heartbeat"
    safety_shutdown_triggered = False

    while True:
        try:
            gpio_states: Dict[int, int] = gpio_manager.get_states()
            device_status: List[Dict[str, Any]] = gpio_manager.get_devices_status()

            heartbeat_payload = {
                "uuid": settings.RASPBERRY_UUID,
                "status": "online",
                "timestamp": int(datetime.now(timezone.utc).timestamp()),
                "gpio_count": len(gpio_states),
                "device_count": len(device_status),
                "gpio": gpio_states,
                "devices": device_status,
            }

            message = {
                "event_type": EventType.HEARTBEAT.value,
                "payload": heartbeat_payload,
            }

            # JETSTREAM — PUBLISH
            await nats_client.js_publish(subject, message)

            logging.info(
                f"[HEARTBEAT] subject={subject} | payload: {message}"
            )
            safety_shutdown_triggered = False

        except Exception as e:
            logging.exception(f"Heartbeat error: {e}")
            if not safety_shutdown_triggered:
                logging.warning("Heartbeat failed; triggering safety shutdown (all devices OFF).")
                gpio_manager.force_all_off(reason="HEARTBEAT_FAILURE")
                safety_shutdown_triggered = True

        await asyncio.sleep(settings.HEARTBEAT_INTERVAL)
