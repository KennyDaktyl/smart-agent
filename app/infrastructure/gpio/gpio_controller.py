import logging
from app.infrastructure.gpio.hardware import GPIO

logger = logging.getLogger(__name__)


class GPIOController:
    """
    Thin hardware abstraction layer over RPi.GPIO.
    No domain logic. No device identifiers. No config awareness.
    """

    def __init__(self):
        try:
            GPIO.setwarnings(False)
            GPIO.setmode(GPIO.BCM)
            logger.info("GPIO initialized in BCM mode")
        except Exception as e:
            logger.exception(f"GPIO initialization failed: {e}")

    def initialize_pin(self, gpio: int, active_low: bool) -> None:
        """
        Configure GPIO as output and set safe OFF state.
        """
        try:
            GPIO.setup(gpio, GPIO.OUT)

            # Safe default: OFF
            value = GPIO.HIGH if active_low else GPIO.LOW
            GPIO.output(gpio, value)

            logger.info(
                f"Initialized GPIO {gpio} to OFF (active_low={active_low})"
            )

        except Exception:
            logger.exception(f"Failed to initialize GPIO {gpio}")

    def read(self, gpio: int) -> int:
        """
        Read raw GPIO value.
        """
        try:
            return GPIO.input(gpio)
        except Exception:
            logger.exception(f"GPIO read error on pin {gpio}")
            return GPIO.HIGH  # safe fallback

    def write(self, gpio: int, is_on: bool, active_low: bool) -> None:
        """
        Write logical ON/OFF to GPIO considering active_low.
        """
        try:
            if active_low:
                value = GPIO.LOW if is_on else GPIO.HIGH
            else:
                value = GPIO.HIGH if is_on else GPIO.LOW

            GPIO.output(gpio, value)

        except Exception:
            logger.exception(f"GPIO write error on pin {gpio}")

    def cleanup(self):
        """
        Cleanup GPIO (optional, for shutdown).
        """
        try:
            GPIO.cleanup()
            logger.info("GPIO cleanup completed")
        except Exception:
            logger.exception("GPIO cleanup failed")


gpio_controller = GPIOController()
