# app/main.py

import asyncio
import logging
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from app.core.config import settings
from app.core.gpio_monitor import monitor_gpio_changes
from app.core.heartbeat import send_heartbeat
from app.core.nats_client import nats_client
from app.infrastructure.gpio.gpio_config_storage import gpio_config_storage
from app.infrastructure.gpio.gpio_controller import gpio_controller
from app.infrastructure.gpio.gpio_manager import gpio_manager
from app.interfaces.handlers.nats_event_handler import nats_event_handler

logging.basicConfig(level=logging.INFO)


async def main():

    try:
        await nats_client.connect()

        devices = gpio_config_storage.load()
        gpio_controller.load_from_entities(devices)
        gpio_manager.load_devices(devices)
        gpio_controller.turn_all_off()

        await nats_client.subscribe_js(
            f"raspberry.{settings.RASPBERRY_UUID}.events", nats_event_handler
        )

        asyncio.create_task(send_heartbeat())
        # asyncio.create_task(monitor_gpio_changes())

        logging.info("🚀 Raspberry Agent started")

        await asyncio.Future()

    except asyncio.CancelledError:
        pass

    except KeyboardInterrupt:
        logging.info("🛑 Agent Raspberry stopping due to keyboard interrupt.")

    finally:
        try:
            await nats_client.close()
        except Exception:
            pass

        logging.info("Closing GPIO controller.")


if __name__ == "__main__":
    asyncio.run(main())
