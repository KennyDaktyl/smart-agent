from app.domain.gpio.gpio_device_config import GPIODeviceConfig


class GPIOMapper:

    @staticmethod
    def from_dict(data: dict) -> GPIODeviceConfig:
        return GPIODeviceConfig(
            device_id=data["device_id"],
            pin_number=data["pin_number"],
            mode=data["mode"],
            power_threshold_w=data.get("power_threshold_w"),
        )
