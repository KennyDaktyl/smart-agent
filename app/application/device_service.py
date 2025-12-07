import logging
from typing import List, Optional

from app.domain.device.enums import DeviceMode
from app.domain.events.device_events import (DeviceCommandPayload, DeviceCreatedPayload,
                                             DeviceDeletePayload, DeviceUpdatedPayload)
from app.domain.gpio.entities import GPIODevice
from app.infrastructure.backend.backend_adapter import backend_adapter
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
        devices: List[GPIODevice] = gpio_config_storage.load()

        pin_number, active_low = pin_mapping.get_pin_config(payload.device_number)

        new_device = GPIODevice(
            device_id=payload.device_id,
            pin_number=pin_number,
            mode=DeviceMode(payload.mode),
            power_threshold_kw=payload.threshold_kw,
            device_number=payload.device_number,
            active_low=active_low,
        )

        devices.append(new_device)
        gpio_config_storage.save(devices)

        gpio_controller.load_from_entities(devices)
        gpio_manager.load_devices(devices)

        logger.info(
            f"[CREATE] device_id={payload.device_id} "
            f"(device_number={payload.device_number} → pin={pin_number}) "
            f"mode={payload.mode}, threshold={payload.threshold_kw}"
        )

    def update_device(self, payload: DeviceUpdatedPayload):
        """
        payload: DeviceUpdatedPayload
        """

        devices: List[GPIODevice] = gpio_config_storage.load()
        updated = False

        for device in devices:
            if device.device_id == payload.device_id:
                device.mode = DeviceMode(payload.mode)
                device.power_threshold_kw = payload.threshold_kw
                updated = True
                break

        if not updated:
            logger.error(f"[UPDATE] device_id={payload.device_id} NOT FOUND")
            return False

        gpio_config_storage.save(devices)

        gpio_controller.load_from_entities(devices)
        gpio_manager.load_devices(devices)

        logger.info(
            f"[UPDATE] device_id={payload.device_id} mode={payload.mode} threshold={payload.threshold_kw}"
        )
        return True

    def delete_device(self, payload: DeviceDeletePayload):
        """payload: { device_id }"""

        devices: List[GPIODevice] = gpio_config_storage.load()
        before = len(devices)

        devices = [d for d in devices if d.device_id != payload.device_id]

        if len(devices) == before:
            logger.error(f"[DELETE] device_id={payload.device_id} NOT FOUND")
            return False

        gpio_config_storage.save(devices)

        gpio_controller.load_from_entities(devices)
        gpio_manager.load_devices(devices)

        logger.info(f"[DELETE] device_id={payload.device_id} removed")
        return True

    def set_manual_state(self, payload: DeviceCommandPayload):
        """
        payload: DeviceCommandPayload
        Obsługuje TYLKO DeviceMode.MANUAL
        """

        logger.info(f"[MANUAL] SET_STATE → device_id={payload.device_id}, is_on={payload.is_on}")

        devices: List[GPIODevice] = gpio_config_storage.load()
        device: Optional[GPIODevice] = next(
            (d for d in devices if d.device_id == payload.device_id), None
        )

        if not device:
            logger.error(f"[MANUAL] device_id={payload.device_id} NOT FOUND")
            return False

        if device.mode != DeviceMode.MANUAL:
            logger.info(
                f"[MANUAL] IGNORE → device_id={device.device_id} is in mode={device.mode} "
                f"(only MANUAL can execute SET_STATE)"
            )
            return False

        ok = gpio_controller.set_state(device.device_id, payload.is_on)
        if not ok:
            return False

        backend_adapter.log_device_event(
            device_id=device.device_id,
            pin_state=payload.is_on,
            trigger_reason="DEVICE_COMMAND",
        )

        return True

    def set_auto_state(self, device: GPIODevice, current_power: float):
        """
        Wywoływane TYLKO przez auto_power_service.handle_power_reading()

        device: GPIODevice
        current_power: float
        """

        threshold = device.power_threshold_kw

        if threshold is None:
            logger.warning(f"[AUTO] device_id={device.device_id} has no threshold → skipping")
            return False

        should_turn_on = current_power >= threshold

        logger.info(
            f"[AUTO] device_id={device.device_id} power={current_power}, "
            f"threshold={threshold} → {'ON' if should_turn_on else 'OFF'}"
        )

        return gpio_controller.set_state(device.device_id, should_turn_on)


gpio_service = GPIOService()
