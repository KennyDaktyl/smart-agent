import logging

from app.domain.device.enums import DeviceMode
from app.infrastructure.gpio.gpio_config_storage import gpio_config_storage
from app.infrastructure.gpio.gpio_controller import gpio_controller
from app.schemas.device_events import PowerReadingEvent

logger = logging.getLogger(__name__)


class AutoPowerService:

    async def handle_power_reading(self, event: PowerReadingEvent):
        power = event.power_w

        devices = gpio_config_storage.load()

        for d in devices:
            if d.device_id not in event.device_ids:
                continue

            if d.mode != DeviceMode.AUTO_POWER.value:
                continue

            threshold = d.power_threshold_kw or 0

            if power >= threshold:
                gpio_controller.set_state(d.device_id, True)
                logger.info(f"AUTO ON device {d.device_id}")
            else:
                gpio_controller.set_state(d.device_id, False)
                logger.info(f"AUTO OFF device {d.device_id}")


auto_power_service = AutoPowerService()
