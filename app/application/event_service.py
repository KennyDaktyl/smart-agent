# app/application/event_service.py
import logging
from typing import Union

from app.application.gpio_service import gpio_service
from app.application.power_reading_service import power_reading_service
from app.domain.events.device_events import (
    DeviceCommandEvent,
    DeviceCreatedEvent,
    DeviceDeletedEvent,
    DeviceUpdatedEvent,
    EventType,
    PowerReadingEvent,
)

logging = logging.getLogger(__name__)

AnyEvent = Union[
    DeviceCreatedEvent,
    DeviceUpdatedEvent,
    DeviceDeletedEvent,
    PowerReadingEvent,
    DeviceCommandEvent,
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

            case _:
                logging.warning(f"Unknown event type: {event.event_type}")
                return None

    async def _handle_device_created(self, event: DeviceCreatedEvent):
        logging.info(f"Creating device -> {event.data}")
        return gpio_service.create_device(event.data)

    async def _handle_device_updated(self, event: DeviceUpdatedEvent):
        logging.info(f"Updating device -> {event.data}")
        return gpio_service.update_device(event.data)

    async def _handle_device_deleted(self, event: DeviceDeletedEvent):
        logging.info(f"Deleting device -> {event.data}")
        return gpio_service.delete_device(event.data)

    async def _handle_power_reading(self, event: PowerReadingEvent):
        logging.info(f"Handling power reading -> {event.data}")
        await power_reading_service.handle_power(
            power=event.data.power_w,
            unit="W",
        )
        return True

    async def _handle_device_command(self, event: DeviceCommandEvent):
        logging.info(f"Executing device command -> {event.data}")
        return gpio_service.set_manual_state(event.data)


event_service = EventService()
