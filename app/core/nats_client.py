import json
import logging

import nats

from app.core.config import settings

logging = logging.getLogger(__name__)


class NATSClient:
    def __init__(self):
        self.nc = None
        self.js = None

    async def connect(self):
        logging.info(f"Connecting to NATS: {settings.NATS_URL}")
        self.nc = await nats.connect(settings.NATS_URL)
        self.js = self.nc.jetstream()

        logging.info("Connected to NATS & JetStream")

        try:
            await self.js.stream_info("device_communication")
            logging.info("Stream device_communication found.")
        except Exception:
            logging.error("Stream device_communication not found!")
            raise RuntimeError("JetStream stream 'device_communication' must be created by backend.")

    async def ensure_connected(self):
        if not self.nc or not self.nc.is_connected:
            await self.connect()

    async def js_publish(self, subject: str, payload: dict):
        await self.ensure_connected()

        data = json.dumps(payload).encode("utf-8")
        await self.js.publish(subject, data)

    async def publish_raw(self, subject: str, payload: dict):
        await self.ensure_connected()
        data = json.dumps(payload).encode("utf-8")
        await self.nc.publish(subject, data)

    async def subscribe(self, subject: str, handler):
        await self.ensure_connected()

        sub = await self.nc.subscribe(subject, cb=handler)
        logging.info(f"[NATS] Subscribed to subject: {subject}")

        return sub
    
    async def subscribe_js(self, subject: str, handler):
        await self.ensure_connected()
        durable = subject.replace(".", "_")
        return await self.js.subscribe(subject, durable=durable, cb=handler)

    async def close(self):
        if self.nc is None:
            return

        try:
            logging.info("Closing NATS connection...")
            await self.nc.drain()
        except Exception:
            pass

        try:
            await self.nc.close()
        except Exception:
            pass

        logging.info("NATS connection closed.")


nats_client = NATSClient()
