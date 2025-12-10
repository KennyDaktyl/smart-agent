# app/infrastructure/gpio/gpio_controller.py
import logging

from app.domain.gpio.entities import GPIODevice
from app.infrastructure.gpio.hardware import GPIO

logging = logging.getLogger(__name__)


class GPIOController:

    def __init__(self):
        self.pin_map: dict[str, int] = {}
        self.active_low_map: dict[str, bool] = {}

        try:
            GPIO.setwarnings(False)
            GPIO.setmode(GPIO.BCM)
        except Exception as e:
            logging.error(f"GPIO init problem: {e}")

    def initialize_pins(self):
        for device_id, pin in self.pin_map.items():
            GPIO.setup(pin, GPIO.OUT)
            active_low = self.active_low_map.get(device_id, True)
            try:
                # Default every pin to OFF on startup for safety.
                GPIO.output(pin, GPIO.HIGH if active_low else GPIO.LOW)
                logging.info(f"GPIOController: init device {device_id} (pin {pin}) to OFF (active_low={active_low})")
            except Exception as e:
                logging.error(f"GPIOController: Error forcing OFF pin {pin}: {e}")

    def load_from_entities(self, devices: list[GPIODevice]):
        self.pin_map = {str(device.device_id): device.pin_number for device in devices}
        self.active_low_map = {str(device.device_id): bool(device.active_low) for device in devices}
        logging.info(f"GPIOController: loaded pin mapping {self.pin_map} with active_low {self.active_low_map}")

    def read_pin(self, pin: int) -> int:
        try:
            return GPIO.input(pin)
        except Exception as e:
            logging.exception(f"GPIO read error on pin {pin}")
            return GPIO.HIGH

    def direct_pin_control(self, gpio_pin: int, is_on: bool, active_low: bool) -> bool:
        try:
            GPIO.setup(gpio_pin, GPIO.OUT)

            if active_low:
                value = GPIO.LOW if is_on else GPIO.HIGH
            else:
                value = GPIO.HIGH if is_on else GPIO.LOW

            GPIO.output(gpio_pin, value)
            return True

        except Exception as e:
            logging.exception(f"GPIO direct control error on pin {gpio_pin}")
            return False

    def set_state(self, device_id: int, is_on: bool):
        pin = self.pin_map.get(str(device_id))
        if pin is None:
            logging.error(f"No pin mapped for device_id={device_id}")
            return False

        active_low = self.active_low_map.get(str(device_id), True)

        return self.direct_pin_control(pin, is_on, active_low)


gpio_controller = GPIOController()
