# app/main.py
import asyncio
import logging
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))
import inspect
from app.core.config import settings
from app.core.gpio_monitor import monitor_gpio_changes
from app.core.heartbeat import send_heartbeat
from app.core.nats_client import nats_client
from app.infrastructure.gpio.gpio_config_storage import gpio_config_storage
from app.infrastructure.gpio.gpio_controller import gpio_controller
from app.infrastructure.gpio.gpio_manager import gpio_manager
from app.interfaces.handlers.nats_event_handler import nats_event_handler
from app.interfaces.handlers.power_reading_handler import inverter_production_handler

from app.core.logging_config import logger


async def main():

    try:
        await nats_client.connect()
        
        logger.warning("=== LOADED CODE FOR get_devices_status() ===")
        logger.warning(inspect.getsource(gpio_manager.get_devices_status))

        devices = gpio_config_storage.load()

        raw = gpio_config_storage.load_raw()
        gpio_controller.active_low = raw.get("active_low", True)
        
        gpio_controller.load_from_entities(devices)

        gpio_manager.load_devices(devices)

        gpio_controller.initialize_pins()

        inverter_serial = gpio_config_storage.get_inverter_serial()
        if not inverter_serial:
            raise RuntimeError("INVERTER_SERIAL not set in config.json!")

        subject = f"device_communication.inverter.{inverter_serial}.production.update"
        await nats_client.subscribe(subject, inverter_production_handler)
        logger.info(f"Subscribed to inverter power updates: {subject}")
        
        subject = f"device_communication.raspberry.{settings.RASPBERRY_UUID}.events"
        await nats_client.subscribe_js(subject, nats_event_handler)
        logger.info(f"Subscribed to Raspberry events. Subject: {subject}")

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
