import logging
from typing import List

from app.domain.device.enums import DeviceMode
from app.domain.events.inverter_events import InverterProductionEvent
from app.domain.gpio.entities import GPIODevice
from app.infrastructure.backend.backend_adapter import backend_adapter
from app.infrastructure.gpio.gpio_config_storage import gpio_config_storage
from app.infrastructure.gpio.gpio_manager import gpio_manager
from app.infrastructure.gpio.gpio_controller import gpio_controller
from app.infrastructure.gpio.hardware import GPIO

logging = logging.getLogger(__name__)


class PowerReadingService:

    def _get_auto_power_devices(self) -> List[GPIODevice]:
        return [
            device
            for device in gpio_manager.devices.values()
            if device.mode == DeviceMode.AUTO_POWER
        ]

    async def handle_inverter_power(self, event: InverterProductionEvent) -> None:
        power = event.payload.active_power
        logging.info(f"Received inverter power = {power} W")
        power_kw = power

        if power is None:
            logging.warning("Active power missing. Forcing all AUTO_POWER devices OFF for safety.")
            for device in self._get_auto_power_devices():
                if gpio_controller.set_state(device.device_id, False):
                    gpio_manager.set_state(device.device_id, False)
                    gpio_config_storage.update_state(device.device_id, False)
                    backend_adapter.log_device_event(
                        device_id=device.device_id,
                        pin_state=False,
                        trigger_reason="POWER_MISSING",
                        power_kw=power_kw,
                    )
            return

        auto_devices: List[GPIODevice] = self._get_auto_power_devices()

        if not auto_devices:
            logging.info("No AUTO_POWER devices. Nothing to do.")
            return

        pin_states = gpio_manager.get_states()

        for device in auto_devices:
            device_id = device.device_id
            pin = device.pin_number
            threshold = device.power_threshold_kw

            logging.info(
                f"AUTO_POWER device_id={device_id}, pin={pin}, "
                f"threshold={threshold}, raw_pin_state={pin_states.get(pin)}"
            )

            if threshold is None:
                logging.error(
                    f"Device {device_id} has AUTO_POWER mode but NO threshold_kw!"
                )
                continue

            should_turn_on: bool = power >= threshold

            raw = pin_states.get(pin)
            if raw is None:
                logging.warning(f"Pin state missing for device_id={device_id} pin={pin}. Forcing OFF.")
                if gpio_controller.set_state(device_id, False):
                    gpio_manager.set_state(device_id, False)
                    gpio_config_storage.update_state(device_id, False)
                continue

            current_is_on = gpio_manager.raw_to_is_on(device, raw)

            logging.info(
                f"[STATE] device_id={device_id} current_is_on={current_is_on}, "
                f"should_turn_on={should_turn_on}, active_low={device.active_low}"
            )

            if current_is_on == should_turn_on:
                logging.info(
                    f"Device {device_id} already in correct state. Skipping."
                )
                continue

            logging.info(
                f"Changing state for device {device_id}: "
                f"pin={pin}, from={current_is_on} → to={should_turn_on}"
            )

            ok = gpio_controller.set_state(device_id, should_turn_on)
            if ok:
                gpio_manager.set_state(device_id, should_turn_on)
                gpio_config_storage.update_state(device_id, should_turn_on)
                backend_adapter.log_device_event(
                    device_id=device_id,
                    pin_state=should_turn_on,
                    trigger_reason="AUTO_TRIGGER",
                    power_kw=power_kw,
                )


power_reading_service = PowerReadingService()
