# app/infrastructure/gpio/gpio_manager.py
import logging
from typing import Dict, List, Optional

from app.core.config import settings
from app.core.nats_client import nats_client
from app.domain.gpio.entities import GPIODevice
from app.infrastructure.gpio.gpio_controller import gpio_controller
from app.infrastructure.gpio.hardware import GPIO

logger = logging.getLogger(__name__)


class GPIOManager:

    def __init__(self):
        self.devices: Dict[str, GPIODevice] = {}

        self.previous_states: Dict[int, Optional[int]] = {}

    def get_device(self, device_id: int) -> Optional[GPIODevice]:
        return self.devices.get(str(device_id))
    
    def load_devices(self, devices: List[GPIODevice]) -> None:
        self.devices = {str(d.device_id): d for d in devices}

        self.previous_states = {d.pin_number: None for d in devices}

        logger.info(f"GPIOManager: loaded {len(devices)} devices")

    def get_states(self) -> Dict[int, int]:
        states: Dict[int, int] = {}

        for device in self.devices.values():
            pin = device.pin_number
            value = gpio_controller.read_pin(pin)
            states[pin] = value

        return states

    def get_devices_status(self):
        logger.warning(f"[DEBUG] get_devices_status() ACTIVE_LOW={gpio_controller.active_low}")

        states = self.get_states()

        results = []
        for d in self.devices.values():
            pin = d.pin_number
            raw = states[pin]

            if gpio_controller.active_low:
                is_on = raw == GPIO.LOW
            else:
                is_on = raw == GPIO.HIGH

            results.append({
                "device_id": d.device_id,
                "pin": d.pin_number,
                "is_on": is_on,
                "mode": d.mode,
                "threshold": d.power_threshold_kw,
            })
            logger.warning(f"[DEBUG] STATUS: device={d.device_id} raw={raw} active_low={gpio_controller.active_low} is_on={is_on}")

        return results


    async def detect_changes(self) -> None:
        current = self.get_states()

        for pin, new_state in current.items():
            old_state = self.previous_states.get(pin)

            if old_state is None:
                self.previous_states[pin] = new_state
                continue

            if new_state != old_state:
                logger.info(f"GPIO change detected on pin {pin}: {old_state} → {new_state}")
                await self.send_change_event(pin, new_state)

            self.previous_states[pin] = new_state

    async def send_change_event(self, pin: int, value: int) -> None:
        payload = {
            "uuid": settings.RASPBERRY_UUID,
            "pin": pin,
            "state": bool(value == 0),
        }

        subject = f"raspberry.{settings.RASPBERRY_UUID}.gpio_change"

        await nats_client.publish(subject, payload)

        logger.info(f"Sent gpio_change event: {payload}")
    
    def set_state(self, device_id: int, is_on: bool) -> bool:
        device = self.get_device(device_id)
        if not device:
            logger.error(f"GPIOManager: device_id={device_id} not found")
            return False

        device.is_on = is_on

        pin = device.pin_number
        self.previous_states[pin] = 0 if is_on else 1

        logger.info(
            f"GPIOManager: logical state updated device_id={device_id}, "
            f"pin={pin}, is_on={is_on}"
        )

        return True


gpio_manager = GPIOManager()
