# app/infrastructure/gpio/gpio_config_storage.py
import json
from pathlib import Path
from typing import Dict, List

from app.core.config import settings
from app.domain.gpio.entities import GPIODevice

DEFAULT_CONFIG = {"raspberry_uuid": None, "device_max": 1, "pins": []}


class GPIOConfigStorage:
    CONFIG_PATH = Path(settings.CONFIG_FILE)

    def load_raw(self) -> Dict:
        if not self.CONFIG_PATH.exists():
            return DEFAULT_CONFIG.copy()

        try:
            with open(self.CONFIG_PATH, "r") as f:
                data = json.load(f)
        except json.JSONDecodeError:
            return DEFAULT_CONFIG.copy()

        merged = DEFAULT_CONFIG.copy()
        merged.update(data)
        return merged

    def load(self) -> List[GPIODevice]:
        data = self.load_raw()
        global_active_low = data.get("active_low")  # backward compatibility

        devices: List[GPIODevice] = []
        for pin_data in data.get("pins", []):
            parsed = pin_data.copy()
            if "active_low" not in parsed and global_active_low is not None:
                parsed["active_low"] = bool(global_active_low)

            devices.append(GPIODevice(**parsed))

        return devices

    def get_inverter_serial(self) -> str | None:
        data = self.load_raw()
        return data.get("inverter_serial")

    def save(self, devices: List[GPIODevice]):

        raw = self.load_raw()
        raw["pins"] = [device.model_dump() for device in devices]

        with open(self.CONFIG_PATH, "w") as f:
            json.dump(raw, f, indent=2)

    def update_device(self, gpio_device: GPIODevice):

        devices = self.load()
        updated = False

        for idx, d in enumerate(devices):
            if d.device_id == gpio_device.device_id:
                devices[idx] = gpio_device
                updated = True
                break

        if not updated:
            devices.append(gpio_device)

        self.save(devices)

    def remove_device(self, device_id: int):
        devices = [d for d in self.load() if d.device_id != device_id]
        self.save(devices)

    def update_state(self, device_id: int, is_on: bool, mode: str = None):
        devices = self.load()

        for d in devices:
            if d.device_id == device_id:
                d.is_on = is_on
            if mode:
                d.mode = mode
        self.save(devices)


gpio_config_storage = GPIOConfigStorage()
