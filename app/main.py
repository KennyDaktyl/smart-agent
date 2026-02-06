# app/main.py
import asyncio
import logging
import sys
from pathlib import Path


sys.path.append(str(Path(__file__).resolve().parent.parent))

# Initialize logging early so subsequent imports inherit the handlers.
from app.core.logging_config import logging

import inspect
from app.core.heartbeat import send_heartbeat
from app.core.nats_client import nats_client
from app.infrastructure.gpio.gpio_config_storage import gpio_config_storage
from app.infrastructure.gpio.gpio_controller import gpio_controller
from app.infrastructure.gpio.gpio_manager import gpio_manager
from app.interfaces.handlers.nats_event_handler import nats_event_handler
from app.interfaces.handlers.power_reading_handler import inverter_production_handler
from app.infrastructure.config.device_config import get_microcontroller_uuid


async def main():

    try:
        await nats_client.connect()

        logging.warning("=== LOADED CODE FOR get_devices_status() ===")
        logging.warning(inspect.getsource(gpio_manager.get_devices_status))

        devices = gpio_config_storage.load()

        gpio_controller.load_from_entities(devices)

        gpio_manager.load_devices(devices)

        gpio_controller.initialize_pins()

        inverter_serial = gpio_config_storage.get_inverter_serial()
        if not inverter_serial:
            raise RuntimeError("INVERTER_SERIAL not set in config.json!")

        subject = (
            f"device_communication.{inverter_serial}.event.provider_current_energy"
        )
        await nats_client.subscribe(subject, inverter_production_handler)
        logging.info(f"Subscribed to inverter power updates: {subject}")

        microcontroller_uuid = get_microcontroller_uuid()
        subject = f"device_communication.events.{microcontroller_uuid}"
        await nats_client.subscribe_js(subject, nats_event_handler)
        logging.info(f"Subscribed to Raspberry events. Subject: {subject}")

        asyncio.create_task(send_heartbeat())

        logging.info("🚀 Raspberry Agent started")

        await asyncio.Event().wait()

    except asyncio.CancelledError:
        pass

    except KeyboardInterrupt:
        logging.info("🛑 Agent Raspberry stopping via keyboard interrupt.")

    finally:
        try:
            await nats_client.close()
        except Exception:
            pass

        logging.info("Closing GPIO controller.")


if __name__ == "__main__":
    asyncio.run(main())
