# app/application/gpio_service.py
import logging

from app.domain.events.device_events import DeviceCreatedPayload
from app.domain.gpio.entities import GPIODevice
from app.infrastructure.gpio.gpio_config_storage import gpio_config_storage
from app.infrastructure.gpio.gpio_controller import gpio_controller
from app.infrastructure.gpio.gpio_manager import gpio_manager
from app.infrastructure.gpio.gpio_pin_mapping import pin_mapping

logger = logging.getLogger(__name__)


class GPIOService:

    def create_device(self, payload: DeviceCreatedPayload):
        """
        payload: DeviceCreatedPayload
        """
        devices = gpio_config_storage.load()

        pin_number = pin_mapping.get_pin(payload.device_number)

        new_device = GPIODevice(
            device_id=payload.device_id,
            device_number=payload.device_number,
            pin_number=pin_number,
            mode=payload.mode,
            power_threshold_kw=payload.threshold_kw,
        )

        devices.append(new_device)
        gpio_config_storage.save(devices)

        # aktualizacja active_low
        gpio_controller.active_low = pin_mapping.is_active_low()

        gpio_controller.load_from_entities(devices)
        gpio_manager.load_devices(devices)

        logger.info(
            f"GPIOService: created device {payload.device_id} "
            f"(device_number={payload.device_number} → pin={pin_number})"
        )

    # -----------------------------------------------------
    # Aktualizacja istniejącego urządzenia
    # -----------------------------------------------------
    def update_device(self, payload):
        devices = gpio_config_storage.load()
        updated = False

        for d in devices:
            if d.device_id == payload.device_id:
                d.mode = payload.mode
                d.power_threshold_kw = payload.threshold_kw
                updated = True

        if not updated:
            logger.error(f"GPIOService: cannot update, device_id={payload.device_id} not found")
            return False

        gpio_config_storage.save(devices)

        gpio_controller.active_low = pin_mapping.is_active_low()
        gpio_controller.load_from_entities(devices)
        gpio_manager.load_devices(devices)

        logger.info(f"GPIOService: updated device {payload.device_id}")
        return True

    def delete_device(self, payload):
        devices = gpio_config_storage.load()
        devices = [d for d in devices if d.device_id != payload.device_id]

        gpio_config_storage.save(devices)

        gpio_controller.active_low = pin_mapping.is_active_low()
        gpio_controller.load_from_entities(devices)
        gpio_manager.load_devices(devices)

        logger.info(f"GPIOService: deleted device {payload.device_id}")
        
    # -----------------------------------------------------
    # Manualne sterowanie przekaźnikiem (DEVICE_COMMAND)
    # -----------------------------------------------------
    def set_manual_state(self, payload):

        logger.info(
            f"GPIOService: manual SET_STATE for device_id={payload.device_id}, is_on={payload.is_on}"
        )

        if payload.command != "SET_STATE":
            logger.error(f"GPIOService: unknown command {payload.command}")
            return False

        ok = gpio_controller.set_state(payload.device_id, payload.is_on)
        if not ok:
            return False

        gpio_manager.set_state(payload.device_id, payload.is_on)

        gpio_config_storage.update_state(payload.device_id, payload.is_on)

        logger.info(
            f"GPIOService: device {payload.device_id} manually set to "
            f"{'ON' if payload.is_on else 'OFF'} (GPIO + manager + config)"
        )

        return True




gpio_service = GPIOService()
