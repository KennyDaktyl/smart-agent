# app/infrastructure/gpio/gpio_pin_mapping.py
import json
import logging
from pathlib import Path

logging = logging.getLogger(__name__)


class PinMapping:

    def __init__(self):
        self.root = Path(__file__).resolve().parents[3]
        self.path = self.root / "gpio_mapping.json"
        self.mapping: dict[str, dict] = {}

        self.load()

    def load(self):
        if not self.path.exists():
            raise RuntimeError(
                f"Missing required GPIO pin mapping file: {self.path}\n"
                "Create gpio_mapping.json in project root."
            )

        try:
            with open(self.path, "r") as f:
                self.mapping = json.load(f)
        except Exception as e:
            raise RuntimeError(f"Failed to load gpio_mapping.json: {e}")

        if "device_pin_map" not in self.mapping:
            raise RuntimeError("gpio_mapping.json must contain 'device_pin_map' section.")

        logging.info(f"Loaded GPIO mapping from {self.path}")

    def get_pin_config(self, device_number: int) -> tuple[int, bool]:
        raw = self.mapping["device_pin_map"].get(str(device_number))
        if raw is None:
            raise ValueError(
                f"gpio_mapping.json: device_number {device_number} has no assigned GPIO pin."
            )

        if isinstance(raw, int):
            # backward compatibility: default active_low=True when only pin is provided
            return raw, True

        if isinstance(raw, dict):
            if "pin" not in raw:
                raise ValueError(f"gpio_mapping.json entry for device_number {device_number} missing 'pin'")
            pin = raw["pin"]
            active_low = bool(raw.get("active_low", True))
            return pin, active_low

        raise ValueError(f"gpio_mapping.json entry for device_number {device_number} has invalid format: {raw}")

    def get_pin(self, device_number: int) -> int:
        pin, _ = self.get_pin_config(device_number)
        return pin


pin_mapping = PinMapping()
