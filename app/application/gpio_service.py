import logging
from app.infrastructure.gpio.gpio_manager import gpio_manager

logger = logging.getLogger(__name__)


class GPIOService:

    def create_device(self, runtime_device):
        """
        runtime_device: RuntimeDevice
        """
        gpio_manager.devices_by_number[runtime_device.device_number] = runtime_device

        logger.info(
            f"Device created: number={runtime_device.device_number}, id={runtime_device.device_id}"
        )

    def update_device(self, device_number: int, **kwargs):
        device = gpio_manager.get_by_number(device_number)
        if not device:
            return False

        for key, value in kwargs.items():
            setattr(device, key, value)

        logger.info(f"Device updated: {device_number}")
        return True

    def delete_device(self, device_number: int):
        device = gpio_manager.get_by_number(device_number)
        if not device:
            return False

        del gpio_manager.devices_by_number[device_number]

        logger.info(f"Device deleted: {device_number}")
        return True

    def set_manual_state(self, device_number: int, is_on: bool):
        return gpio_manager.set_state_by_number(device_number, is_on)


gpio_service = GPIOService()
