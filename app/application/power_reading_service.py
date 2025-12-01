import logging
from typing import List

from app.domain.device.enums import DeviceMode
from app.domain.events.inverter_events import InverterProductionEvent
from app.domain.gpio.entities import GPIODevice
from app.infrastructure.gpio.gpio_manager import gpio_manager
from app.infrastructure.gpio.gpio_controller import gpio_controller
from app.infrastructure.gpio.hardware import GPIO

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
                f"threshold={threshold}, raw_pin_state={pin_states.get(pin)}"
            )

            if threshold is None:
                logger.error(
                    f"Device {device_id} has AUTO_POWER mode but NO threshold_kw!"
                )
                continue

            should_turn_on: bool = power >= threshold

            raw = pin_states.get(pin)

            if gpio_controller.active_low:
                current_is_on = (raw == GPIO.LOW)
            else:
                current_is_on = (raw == GPIO.HIGH)

            logger.info(
                f"[STATE] device_id={device_id} current_is_on={current_is_on}, "
                f"should_turn_on={should_turn_on}, active_low={gpio_controller.active_low}"
            )

            if current_is_on == should_turn_on:
                logger.info(
                    f"Device {device_id} already in correct state. Skipping."
                )
                continue

            logger.info(
                f"Changing state for device {device_id}: "
                f"pin={pin}, from={current_is_on} → to={should_turn_on}"
            )

            gpio_controller.set_state(device_id, should_turn_on)


power_reading_service = PowerReadingService()
