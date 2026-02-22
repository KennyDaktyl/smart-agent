import logging
from typing import Dict, List, Optional

from app.domain.gpio.runtime_device import RuntimeDevice
from app.domain.models.agent_config import DeviceMode
from app.infrastructure.gpio.gpio_controller import gpio_controller
from app.infrastructure.gpio.hardware import GPIO

logger = logging.getLogger(__name__)


class GPIOManager:
    """
    Runtime logic layer.
    No NATS. No backend. No config persistence.
    """

    def __init__(self):
        self.devices_by_number: Dict[int, RuntimeDevice] = {}

    # =========================
    # BOOTSTRAP
    # =========================

    def load_devices(self, devices: List[RuntimeDevice]) -> None:
        seen_numbers: set[int] = set()

        for device in devices:
            if device.device_number in seen_numbers:
                raise RuntimeError(
                    f"Duplicate device_number detected: {device.device_number}"
                )

            seen_numbers.add(device.device_number)

        self.devices_by_number = {d.device_number: d for d in devices}

        for device in devices:
            gpio_controller.initialize_pin(device.gpio, device.active_low)

            mode = device.mode.value if hasattr(device.mode, "value") else str(device.mode)
            if mode == DeviceMode.MANUAL.value and device.desired_state is not None:
                gpio_controller.write(
                    device.gpio,
                    bool(device.desired_state),
                    device.active_low,
                )

        logger.info(f"GPIOManager loaded {len(devices)} devices")

    # =========================
    # LOOKUPS
    # =========================

    def get_by_number(self, device_number: int) -> Optional[RuntimeDevice]:
        return self.devices_by_number.get(device_number)

    # =========================
    # STATE HELPERS
    # =========================

    def raw_to_is_on(self, device: RuntimeDevice, raw: int) -> bool:
        if device.active_low:
            return raw == GPIO.LOW
        return raw == GPIO.HIGH

    def read_is_on_by_number(self, device_number: int) -> bool:
        device = self.get_by_number(device_number)
        if not device:
            return False

        raw = gpio_controller.read(device.gpio)
        return self.raw_to_is_on(device, raw)

    # =========================
    # STATUS
    # =========================

    def get_devices_status(self) -> List[dict]:
        result = []

        for device in self.devices_by_number.values():
            raw = gpio_controller.read(device.gpio)
            is_on = self.raw_to_is_on(device, raw)

            mode = (
                device.mode.value if hasattr(device.mode, "value") else str(device.mode)
            )

            result.append(
                {
                    "device_id": device.device_id,
                    "device_number": device.device_number,
                    "gpio": device.gpio,
                    "is_on": is_on,
                    "mode": mode,
                }
            )

        return result

    # =========================
    # CONTROL
    # =========================

    def set_state_by_number(self, device_number: int, is_on: bool) -> bool:
        device = self.get_by_number(device_number)

        if not device:
            logger.error(f"Device number {device_number} not found")
            return False

        gpio_controller.write(device.gpio, is_on, device.active_low)
        device.desired_state = is_on

        logger.info(f"Device number {device_number} set to {'ON' if is_on else 'OFF'}")

        return True

    def force_all_off(self, reason: str = "SAFETY") -> None:
        logger.warning(f"Forcing all devices OFF due to {reason}")

        for device in self.devices_by_number.values():
            gpio_controller.write(device.gpio, False, device.active_low)
            device.desired_state = False


gpio_manager = GPIOManager()
