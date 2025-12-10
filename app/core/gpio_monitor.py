# app/core/gpio_monitor.py

import asyncio
import logging

from app.infrastructure.gpio.gpio_manager import gpio_manager

logging = logging.getLogger(__name__)


async def monitor_gpio_changes() -> None:
    await asyncio.sleep(2)

    logging.info("GPIO monitor started")

    while True:
        try:
            await gpio_manager.detect_changes()
        except Exception as e:
            logging.exception(f"GPIO monitoring error: {e}")

        await asyncio.sleep(0.5)
