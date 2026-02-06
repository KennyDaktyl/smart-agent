import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List
from pathlib import Path

from app.core.config import settings
from app.core.nats_client import nats_client
from app.domain.events.enums import EventType
from app.infrastructure.config.device_config import get_microcontroller_uuid
from app.infrastructure.gpio.gpio_manager import gpio_manager
from app.infrastructure.gpio.gpio_config_storage import gpio_config_storage
from app.infrastructure.gpio.gpio_controller import gpio_controller

logging = logging.getLogger(__name__)


async def send_heartbeat() -> None:

    await asyncio.sleep(1)

    microcontroller_uuid = get_microcontroller_uuid()

    subject = (
        f"device_communication.{microcontroller_uuid}.event.microcontroller_heartbeat"
    )
    safety_shutdown_triggered = False

    while True:
        try:
            # Always read from config file to avoid stale in-memory state.
            devices = gpio_config_storage.load()

            gpio_states: Dict[int, int] = {}
            device_status: List[Dict[str, Any]] = []

            for device in devices:
                pin = device.pin_number
                raw = gpio_controller.read_pin(pin)
                gpio_states[pin] = raw
                is_on = gpio_manager.raw_to_is_on(device, raw)

                device_status.append(
                    {
                        "device_id": device.device_id,
                        "pin": pin,
                        "is_on": is_on,
                        "mode": device.mode.value if hasattr(device.mode, "value") else device.mode,
                        "threshold": device.power_threshold_kw,
                    }
                )

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
                "subject": subject,
                "payload": heartbeat_payload,
            }

            # JETSTREAM — PUBLISH
            await nats_client.js_publish(subject, message)

            logging.info(f"[HEARTBEAT] subject={subject} | payload: {message}")
            safety_shutdown_triggered = False

        except Exception as e:
            logging.exception(f"Heartbeat error: {e}")
            if not safety_shutdown_triggered:
                logging.warning(
                    "Heartbeat failed; triggering safety shutdown (all devices OFF)."
                )
                gpio_manager.force_all_off(reason="HEARTBEAT_FAILURE")
                safety_shutdown_triggered = True

        await asyncio.sleep(settings.HEARTBEAT_INTERVAL)
