# app/application/event_service.py
import logging
from typing import Union

from app.application.gpio_service import gpio_service
from app.application.microcontroller_command_service import (
    microcontroller_command_service,
)
from app.application.power_reading_service import power_reading_service
from app.application.provider_service import provider_service
from app.domain.events.device_events import (
    DeviceCommandEvent,
    DeviceCreatedEvent,
    DeviceDeletedEvent,
    MicrocontrollerCommandEvent,
    DeviceUpdatedEvent,
    EventType,
    ProviderUpdatedEvent,
    PowerReadingEvent,
)

logging = logging.getLogger(__name__)

AnyEvent = Union[
    DeviceCreatedEvent,
    DeviceUpdatedEvent,
    DeviceDeletedEvent,
    PowerReadingEvent,
    DeviceCommandEvent,
    ProviderUpdatedEvent,
    MicrocontrollerCommandEvent,
]


class EventService:

    async def handle_event(self, event: AnyEvent):

        logging.info(f"Routing event type={event.event_type}")

        match event.event_type:

            case EventType.DEVICE_CREATED:
                return await self._handle_device_created(event)

            case EventType.DEVICE_UPDATED:
                return await self._handle_device_updated(event)

            case EventType.DEVICE_DELETED:
                return await self._handle_device_deleted(event)

            case EventType.CURRENT_ENERGY:
                return await self._handle_power_reading(event)

            case EventType.DEVICE_COMMAND:
                return await self._handle_device_command(event)

            case EventType.MICROCONTROLLER_COMMAND:
                return await self._handle_microcontroller_command(event)

            case EventType.PROVIDER_UPDATED:
                return await self._handle_provider_updated(event)

            case _:
                logging.warning(f"Unknown event type: {event.event_type}")
                return None

    async def _handle_device_created(self, event: DeviceCreatedEvent):
        logging.info(
            "Creating device -> device_id=%s device_uuid=%s device_number=%s mode=%s "
            "rated_power=%s threshold_value=%s auto_rule=%s is_on=%s",
            event.data.device_id,
            event.data.device_uuid,
            event.data.device_number,
            event.data.mode,
            event.data.rated_power,
            event.data.threshold_value,
            event.data.auto_rule.model_dump() if event.data.auto_rule else None,
            event.data.is_on,
        )
        return gpio_service.create_device(event.data)

    async def _handle_device_updated(self, event: DeviceUpdatedEvent):
        logging.info(f"Updating device -> {event.data}")
        return gpio_service.update_device(event.data)

    async def _handle_device_deleted(self, event: DeviceDeletedEvent):
        logging.info(f"Deleting device -> {event.data}")
        return gpio_service.delete_device(event.data)

    async def _handle_power_reading(self, event: PowerReadingEvent):
        logging.info(
            "Handling power reading -> value=%s unit=%s grid_power=%s battery_soc=%s",
            event.data.value,
            event.data.unit,
            event.data.grid_power.value if event.data.grid_power else None,
            event.data.battery_soc.value if event.data.battery_soc else None,
        )
        await power_reading_service.handle_power(event.data)
        return True

    async def _handle_device_command(self, event: DeviceCommandEvent):
        logging.info(f"Executing device command -> {event.data}")
        return gpio_service.set_state_from_command(event.data)

    async def _handle_provider_updated(self, event: ProviderUpdatedEvent):
        logging.info(
            "Updating provider config -> provider_uuid=%s unit=%s has_power_meter=%s "
            "has_energy_storage=%s",
            event.data.provider_uuid,
            event.data.unit,
            event.data.has_power_meter,
            event.data.has_energy_storage,
        )
        return await provider_service.update_provider_uuid(
            event.data.provider_uuid,
            event.data.unit,
            event.data.has_power_meter,
            event.data.has_energy_storage,
        )

    async def _handle_microcontroller_command(self, event: MicrocontrollerCommandEvent):
        logging.info("Executing microcontroller command -> %s", event.data.command)
        return await microcontroller_command_service.handle_command(
            command=event.data.command,
            config_json=event.data.config_json,
            hardware_config_json=event.data.hardware_config_json,
            env_file_content=event.data.env_file_content,
        )


event_service = EventService()
