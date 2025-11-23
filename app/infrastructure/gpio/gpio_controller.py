# app/infrastructure/gpio/gpio_controller.py
import logging

from app.domain.gpio.entities import GPIODevice
from app.infrastructure.gpio.hardware import GPIO

logger = logging.getLogger(__name__)


class GPIOController:

    def __init__(self):
        self.pin_map: dict[str, int] = {}
        self.active_low: bool = True

        try:
            GPIO.setwarnings(False)
            GPIO.setmode(GPIO.BCM)
        except Exception as e:
            logger.error(f"GPIO init problem: {e}")

    def turn_all_off(self):
        for device_id, pin in self.pin_map.items():
            try:
                GPIO.setup(pin, GPIO.OUT)

                if self.active_low:
                    GPIO.output(pin, GPIO.HIGH)
                else:
                    GPIO.output(pin, GPIO.LOW)

                logger.info(f"GPIOController: Forced OFF device {device_id} (pin {pin}) on startup")

            except Exception as e:
                logger.error(f"GPIOController: Error forcing OFF pin {pin}: {e}")

    def load_from_entities(self, devices: list[GPIODevice]):
        self.pin_map = {str(device.device_id): device.pin_number for device in devices}

        for device in devices:
            GPIO.setup(device.pin_number, GPIO.OUT)

            if self.active_low:
                GPIO.output(device.pin_number, GPIO.HIGH)
            else:
                GPIO.output(device.pin_number, GPIO.LOW)

        logger.info(f"GPIOController: loaded pin mapping {self.pin_map}")

    def read_pin(self, pin: int) -> int:
        try:
            GPIO.setup(pin, GPIO.IN)
            return GPIO.input(pin)
        except Exception as e:
            logger.exception(f"GPIO read error on pin {pin}")
            return GPIO.HIGH

    def direct_pin_control(self, gpio_pin: int, is_on: bool) -> bool:
        try:
            GPIO.setup(gpio_pin, GPIO.OUT)

            if self.active_low:
                value = GPIO.LOW if is_on else GPIO.HIGH
            else:
                value = GPIO.HIGH if is_on else GPIO.LOW

            GPIO.output(gpio_pin, value)
            return True

        except Exception as e:
            logger.exception(f"GPIO direct control error on pin {gpio_pin}")
            return False

    def set_state(self, device_id: int, is_on: bool):
        pin = self.pin_map.get(str(device_id))
        if pin is None:
            logger.error(f"No pin mapped for device_id={device_id}")
            return False

        return self.direct_pin_control(pin, is_on)


gpio_controller = GPIOController()
