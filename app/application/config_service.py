import json
import logging

from app.infrastructure.storage.config_storage import CONFIG_PATH

logger = logging.getLogger(__name__)


class ConfigService:

    def load(self):
        if not CONFIG_PATH.exists():
            return {"pins": []}

        with open(CONFIG_PATH) as f:
            return json.load(f)

    def save(self, config):
        with open(CONFIG_PATH, "w") as f:
            json.dump(config, f, indent=2)

    def add_device_to_config(self, device_id, pin, mode, threshold):
        config = self.load()

        config["pins"].append(
            {
                "device_id": device_id,
                "pin_number": pin,
                "mode": mode,
                "power_threshold_w": threshold,
            }
        )

        self.save(config)

    def update_device(self, device_id, mode, threshold):
        config = self.load()

        for pin_cfg in config["pins"]:
            if pin_cfg["device_id"] == device_id:
                pin_cfg["mode"] = mode
                pin_cfg["power_threshold_w"] = threshold

        self.save(config)

    def get_devices_for_inverter(self, inverter_id):
        # TODO: zależnie od backendu
        return []


config_service = ConfigService()
