import asyncio
from datetime import datetime, timezone
from typing import Optional

from app.core.logging_config import logger
from app.core.nats_client import nats_client
from app.core.nats_subjects import NatsSubjects, AgentEvents
from app.infrastructure.config.domain_config_repository import (
    domain_config_repository,
)
from app.infrastructure.gpio.gpio_manager import gpio_manager


class HeartbeatService:

    def __init__(self):
        self._task: Optional[asyncio.Task] = None
        self._running = False

    async def start(self):
        if self._running:
            return

        config = domain_config_repository.load()

        if not config.heartbeat.enabled:
            logger.info("Heartbeat disabled in config.")
            return

        self._interval = config.heartbeat.interval
        self._micro_uuid = config.microcontroller_uuid

        self._running = True
        self._task = asyncio.create_task(self._loop())


    async def stop(self):
        if not self._running:
            return

        logger.info("Stopping heartbeat loop.")
        self._running = False

        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _loop(self):
        safety_shutdown_triggered = False

        subject = NatsSubjects.agent_event(
            self._micro_uuid,
            AgentEvents.HEARTBEAT,
        )

        while self._running:
            try:
                devices = gpio_manager.get_devices_status()

                payload = {
                    "uuid": self._micro_uuid,
                    "status": "online",
                    "timestamp": int(datetime.now(timezone.utc).timestamp()),
                    "devices": devices,
                }

                await nats_client.js_publish(subject, payload)

                safety_shutdown_triggered = False

            except Exception:
                logger.exception("Heartbeat error")

                if not safety_shutdown_triggered:
                    gpio_manager.force_all_off(
                        reason="HEARTBEAT_FAILURE"
                    )
                    safety_shutdown_triggered = True

            await asyncio.sleep(self._interval)



heartbeat_service = HeartbeatService()
