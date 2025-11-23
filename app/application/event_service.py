import logging
from typing import Union

from app.application.auto_power_service import auto_power_service
from app.application.gpio_service import gpio_service
from app.domain.events.device_events import (DeviceCommandEvent, DeviceCreatedEvent,
                                             DeviceUpdatedEvent, EventType, PowerReadingEvent)

logger = logging.getLogger(__name__)

AnyEvent = Union[
    DeviceCreatedEvent,
    DeviceUpdatedEvent,
    PowerReadingEvent,
    DeviceCommandEvent,
]


class EventService:

    async def handle_event(self, event: AnyEvent):

        logger.info(f"Routing event type={event.event_type}")

        match event.event_type:

            case EventType.DEVICE_CREATED:
                return await self._handle_device_created(event)

            case EventType.DEVICE_UPDATED:
                return await self._handle_device_updated(event)

            case EventType.POWER_READING:
                return await self._handle_power_reading(event)

            case EventType.DEVICE_COMMAND:
                return await self._handle_device_command(event)

            case _:
                logger.warning(f"Unknown event type: {event.event_type}")
                return None

    async def _handle_device_created(self, event: DeviceCreatedEvent):
        logger.info(f"Creating device -> {event.payload}")
        gpio_service.create_device(event.payload)
        return True

    async def _handle_device_updated(self, event: DeviceUpdatedEvent):
        logger.info(f"Updating device -> {event.payload}")
        gpio_service.update_device(event.payload)
        return True

    async def _handle_power_reading(self, event: PowerReadingEvent):
        logger.info(f"Handling power reading -> {event.payload}")
        await auto_power_service.handle_power_reading(event.payload)
        return True

    async def _handle_device_command(self, event: DeviceCommandEvent):
        logger.info(f"Executing device command -> {event.payload}")
        gpio_service.set_manual_state(event.payload)
        return True


event_service = EventService()
