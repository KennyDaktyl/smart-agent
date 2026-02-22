# app/application/event_service.py
import logging
from typing import Union

from app.application.gpio_service import gpio_service
from app.application.power_reading_service import power_reading_service
from app.application.provider_service import provider_service
from app.domain.events.device_events import (
    DeviceCommandEvent,
    DeviceCreatedEvent,
    DeviceDeletedEvent,
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

            case EventType.PROVIDER_UPDATED:
                return await self._handle_provider_updated(event)

            case _:
                logging.warning(f"Unknown event type: {event.event_type}")
                return None

    async def _handle_device_created(self, event: DeviceCreatedEvent):
        logging.info(
            "Creating device -> device_id=%s device_uuid=%s device_number=%s mode=%s "
            "rated_power=%s threshold_value=%s is_on=%s",
            event.data.device_id,
            event.data.device_uuid,
            event.data.device_number,
            event.data.mode,
            event.data.rated_power,
            event.data.threshold_value,
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
            "Handling power reading -> value=%s unit=%s",
            event.data.value,
            event.data.unit,
        )
        await power_reading_service.handle_power(value=event.data.value)
        return True

    async def _handle_device_command(self, event: DeviceCommandEvent):
        logging.info(f"Executing device command -> {event.data}")
        return gpio_service.set_manual_state(event.data)

    async def _handle_provider_updated(self, event: ProviderUpdatedEvent):
        logging.info(
            "Updating provider UUID -> provider_uuid=%s",
            event.data.provider_uuid,
        )
        return await provider_service.update_provider_uuid(event.data.provider_uuid)


event_service = EventService()
