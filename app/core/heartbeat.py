import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List

from app.core.config import settings
from app.core.nats_client import nats_client
from app.infrastructure.gpio.gpio_manager import gpio_manager

logger = logging.getLogger(__name__)


async def send_heartbeat() -> None:

    await asyncio.sleep(1)

    subject = f"device_communication.raspberry.{settings.RASPBERRY_UUID}.heartbeat"

    while True:
        try:
            gpio_states: Dict[int, int] = gpio_manager.get_states()
            device_status: List[Dict[str, Any]] = gpio_manager.get_devices_status()

            payload = {
                "uuid": settings.RASPBERRY_UUID,
                "status": "online",
                "timestamp": int(datetime.now(timezone.utc).timestamp()),
                "gpio_count": len(gpio_states),
                "device_count": len(device_status),
                "gpio": gpio_states,
                "devices": device_status,
            }

            # JETSTREAM — PUBLISH
            await nats_client.js_publish(subject, payload)

            logger.info(
                f"[HEARTBEAT] subject={subject} | payload: {payload}"
            )

        except Exception as e:
            logger.exception(f"Heartbeat error: {e}")

        await asyncio.sleep(settings.HEARTBEAT_INTERVAL)
