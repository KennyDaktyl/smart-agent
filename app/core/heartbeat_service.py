import asyncio
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from app.core.logging_config import logger
from app.core.nats_client import nats_client
from app.core.nats_subjects import AgentEvents, NatsSubjects
from app.domain.events.enums import EventType, HeartbeatStatus
from app.infrastructure.config.domain_config_repository import domain_config_repository
from app.infrastructure.gpio.gpio_manager import gpio_manager


class HeartbeatPublishTrigger(str, Enum):
    INTERVAL = "INTERVAL"
    MANUAL = "MANUAL"
    STATE_CHANGE = "STATE_CHANGE"


class HeartbeatFailureReason(str, Enum):
    HEARTBEAT_FAILURE = "HEARTBEAT_FAILURE"


class HeartbeatService:

    def __init__(self):
        self._task: Optional[asyncio.Task] = None
        self._running = False
        self._interval = 60
        self._micro_uuid = ""
        self._publish_lock = asyncio.Lock()

    def _load_runtime_config(self):
        config = domain_config_repository.load()
        self._interval = config.heartbeat_interval
        self._micro_uuid = config.microcontroller_uuid
        return config

    def _build_subject(self) -> str:
        return NatsSubjects.agent_event(
            self._micro_uuid,
            AgentEvents.HEARTBEAT,
        )

    async def _publish_event_payload(
        self,
        *,
        payload: dict,
        trigger: HeartbeatPublishTrigger,
    ) -> None:
        subject = self._build_subject()
        event = {
            "event_type": EventType.HEARTBEAT.value,
            "subject": subject,
            "payload": payload,
        }

        logger.info(
            "Publishing heartbeat | trigger=%s subject=%s payload=%s",
            trigger.value,
            subject,
            event,
        )

        await nats_client.js_publish(subject, event)

    def _build_heartbeat_payload(self) -> dict:
        return {
            "uuid": self._micro_uuid,
            "status": HeartbeatStatus.ONLINE.value,
            "timestamp": int(datetime.now(timezone.utc).timestamp()),
            "heartbeat_interval": self._interval,
            "devices": gpio_manager.get_devices_status(),
        }

    async def start(self):
        if self._running:
            return

        self._load_runtime_config()

        self._running = True
        self._task = asyncio.create_task(self._loop())

    async def publish_now(
        self,
        *,
        trigger: HeartbeatPublishTrigger = HeartbeatPublishTrigger.MANUAL,
    ) -> bool:
        self._load_runtime_config()

        try:
            async with self._publish_lock:
                await self._publish_event_payload(
                    payload=self._build_heartbeat_payload(),
                    trigger=trigger,
                )
            return True
        except Exception:
            logger.exception(
                "Immediate heartbeat publish failed | trigger=%s",
                trigger.value,
            )
            return False

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

        while self._running:
            try:
                async with self._publish_lock:
                    await self._publish_event_payload(
                        payload=self._build_heartbeat_payload(),
                        trigger=HeartbeatPublishTrigger.INTERVAL,
                    )

                safety_shutdown_triggered = False

            except Exception:
                logger.exception("Heartbeat error")

                if not safety_shutdown_triggered:
                    gpio_manager.force_all_off(
                        reason=HeartbeatFailureReason.HEARTBEAT_FAILURE.value,
                    )
                    safety_shutdown_triggered = True

            await asyncio.sleep(self._interval)


heartbeat_service = HeartbeatService()
