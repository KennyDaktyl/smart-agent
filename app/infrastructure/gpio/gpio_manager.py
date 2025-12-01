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

    @staticmethod
    def raw_to_is_on(raw: int) -> bool:
        if gpio_controller.active_low:
            return raw == GPIO.LOW
        else:
            return raw == GPIO.HIGH

    def load_devices(self, devices: List[GPIODevice]) -> None:
        self.devices = {str(d.device_id): d for d in devices}
        self.previous_states = {d.pin_number: None for d in devices}
        logger.info(f"GPIOManager: loaded {len(devices)} devices")

    def get_states(self) -> Dict[int, int]:
        states: Dict[int, int] = {}
        for device in self.devices.values():
            pin = device.pin_number
            val = gpio_controller.read_pin(pin)
            states[pin] = val
        return states

    def get_devices_status(self):
        states = self.get_states()

        results = []
        for d in self.devices.values():
            raw = states[d.pin_number]
            is_on = self.raw_to_is_on(raw)

            results.append({
                "device_id": d.device_id,
                "pin": d.pin_number,
                "is_on": is_on,
                "mode": d.mode,
                "threshold": d.power_threshold_kw,
            })

        return results

    def get_is_on(self, device_id: int) -> bool:
        device = self.devices.get(str(device_id))
        if not device:
            return False

        raw = gpio_controller.read_pin(device.pin_number)
        return self.raw_to_is_on(raw)

    async def detect_changes(self) -> None:
        current = self.get_states()

        for pin, new_raw in current.items():
            old_raw = self.previous_states.get(pin)

            if old_raw is None:
                self.previous_states[pin] = new_raw
                continue

            if new_raw != old_raw:
                logger.info(
                    f"GPIO change on pin {pin}: {old_raw} → {new_raw}"
                )
                await self.send_change_event(pin, new_raw)

            self.previous_states[pin] = new_raw

    async def send_change_event(self, pin: int, raw: int) -> None:
        payload = {
            "uuid": settings.RASPBERRY_UUID,
            "pin": pin,
            "state": self.raw_to_is_on(raw),
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

        if gpio_controller.active_low:
            raw = GPIO.LOW if is_on else GPIO.HIGH
        else:
            raw = GPIO.HIGH if is_on else GPIO.LOW

        self.previous_states[device.pin_number] = raw

        logger.info(
            f"GPIOManager: logical state updated "
            f"device_id={device_id}, pin={device.pin_number}, "
            f"is_on={is_on}, raw={raw}"
        )

        return True


gpio_manager = GPIOManager()
