import logging

from app.domain.device.enums import DeviceMode
from app.infrastructure.gpio.gpio_config_storage import gpio_config_storage
from app.infrastructure.gpio.gpio_controller import gpio_controller
from app.infrastructure.gpio.gpio_manager import gpio_manager
from app.schemas.device_events import PowerReadingEvent

logger = logging.getLogger(__name__)


class AutoPowerService:

    async def handle_power_reading(self, event: PowerReadingEvent):
        power = event.power_w

        devices = gpio_config_storage.load()

        if power is None:
            logger.warning("Power reading missing. Turning all AUTO_POWER devices OFF for safety.")
            for d in devices:
                if d.device_id in event.device_ids and d.mode == DeviceMode.AUTO_POWER.value:
                    ok = gpio_controller.set_state(d.device_id, False)
                    if ok:
                        gpio_manager.set_state(d.device_id, False)
                        gpio_config_storage.update_state(d.device_id, False)
            return

        for d in devices:
            if d.device_id not in event.device_ids:
                continue

            if d.mode != DeviceMode.AUTO_POWER.value:
                continue

            threshold = d.power_threshold_kw or 0

            if power >= threshold:
                ok = gpio_controller.set_state(d.device_id, True)
                if ok:
                    gpio_manager.set_state(d.device_id, True)
                    gpio_config_storage.update_state(d.device_id, True)
                logger.info(f"AUTO ON device {d.device_id}")
            else:
                ok = gpio_controller.set_state(d.device_id, False)
                if ok:
                    gpio_manager.set_state(d.device_id, False)
                    gpio_config_storage.update_state(d.device_id, False)
                logger.info(f"AUTO OFF device {d.device_id}")


auto_power_service = AutoPowerService()
