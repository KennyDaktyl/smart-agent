import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class PinMapping:

    def __init__(self):
        self.root = Path(__file__).resolve().parents[3]
        self.path = self.root / "gpio_mapping.json"
        self.mapping = {}

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

        if "active_low" not in self.mapping:
            raise RuntimeError("gpio_mapping.json must contain 'active_low' field.")

        logger.info(f"Loaded GPIO mapping from {self.path}")

    def get_pin(self, device_number: int) -> int:
        pin = self.mapping["device_pin_map"].get(str(device_number))
        if pin is None:
            raise ValueError(
                f"gpio_mapping.json: device_number {device_number} has no assigned GPIO pin."
            )
        return pin

    def is_active_low(self) -> bool:
        return bool(self.mapping["active_low"])


pin_mapping = PinMapping()
