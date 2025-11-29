import logging
from typing import List

from app.domain.device.enums import DeviceMode
from app.domain.events.inverter_events import InverterProductionEvent
from app.domain.gpio.entities import GPIODevice
from app.infrastructure.gpio.gpio_manager import gpio_manager
from app.infrastructure.gpio.gpio_controller import gpio_controller

logger = logging.getLogger(__name__)


class PowerReadingService:

    def _get_auto_power_devices(self) -> List[GPIODevice]:
        return [
            device
            for device in gpio_manager.devices.values()
            if device.mode == DeviceMode.AUTO_POWER
        ]

    async def handle_inverter_power(self, event: InverterProductionEvent) -> None:
        power: float = event.active_power
        logger.info(f"Received inverter power = {power} W")

        auto_devices: List[GPIODevice] = self._get_auto_power_devices()

        if not auto_devices:
            logger.info("No AUTO_POWER devices. Nothing to do.")
            return

        pin_states = gpio_manager.get_states()

        for device in auto_devices:
            device_id = device.device_id
            pin = device.pin_number
            threshold = device.power_threshold_kw

            logger.info(
                f"AUTO_POWER device_id={device_id}, pin={pin}, "
                f"threshold={threshold}, current_pin_state={pin_states.get(pin)}"
            )

            if threshold is None:
                logger.error(
                    f"Device {device_id} has AUTO_POWER mode but no threshold_kw!"
                )
                continue

            should_turn_on: bool = power >= threshold

            if gpio_controller.active_low:
                expected_gpio_state = 0 if should_turn_on else 1
            else:
                expected_gpio_state = 1 if should_turn_on else 0

            current_gpio_state = pin_states.get(pin)

            if current_gpio_state == expected_gpio_state:
                logger.info(
                    f"Device {device_id} already in correct state "
                    f"(pin={pin}, target={expected_gpio_state}). Skipping."
                )
                continue

            logger.info(
                f"Changing state for device {device_id}: "
                f"pin={pin}, from={current_gpio_state} → to={expected_gpio_state}"
            )

            gpio_controller.set_state(device_id, should_turn_on)


power_reading_service = PowerReadingService()
