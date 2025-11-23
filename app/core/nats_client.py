import json
import logging

import nats
from nats.js.api import RetentionPolicy, StreamConfig

from app.core.config import settings

logger = logging.getLogger(__name__)


class NATSClient:
    def __init__(self):
        self.nc = None
        self.js = None

    async def connect(self):
        logger.info(f"Connecting to NATS: {settings.NATS_URL}")
        self.nc = await nats.connect(settings.NATS_URL)
        self.js = self.nc.jetstream()
        logger.info("Connected to NATS & JetStream")
        await self.ensure_streams()

    async def ensure_streams(self):
        await self.ensure_stream(
            name="raspberry_events", subjects=[f"raspberry.{settings.RASPBERRY_UUID}.events"]
        )

        await self.ensure_stream(
            name="raspberry_heartbeat", subjects=[f"raspberry.{settings.RASPBERRY_UUID}.heartbeat"]
        )

        await self.ensure_stream(
            name="raspberry_gpio", subjects=[f"raspberry.{settings.RASPBERRY_UUID}.gpio_change"]
        )

    async def ensure_stream(self, name: str, subjects: list[str]):
        try:
            await self.js.stream_info(name)
        except Exception:
            cfg = StreamConfig(name=name, subjects=subjects, retention=RetentionPolicy.LIMITS)
            await self.js.add_stream(cfg)

    async def publish(self, subject: str, payload: dict):
        data = json.dumps(payload).encode()
        await self.js.publish(subject, data)

    async def publish_raw(self, subject: str, payload: dict):
        data = json.dumps(payload).encode()
        await self.nc.publish(subject, data)

    async def subscribe_js(self, subject: str, handler):
        durable = subject.replace(".", "_")
        return await self.js.subscribe(subject, durable=durable, cb=handler)

    async def close(self):
        if self.nc is None:
            return

        try:
            logger.info("Closing NATS connection...")
            await self.nc.drain()
        except Exception:
            pass

        try:
            await self.nc.close()
        except Exception:
            pass

        logger.info("NATS connection closed.")


nats_client = NATSClient()
