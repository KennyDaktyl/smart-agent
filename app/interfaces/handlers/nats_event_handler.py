import json
import logging

from app.application.event_service import event_service
from app.core.nats_client import nats_client
from app.core.heartbeat_service import heartbeat_service
from app.domain.events.device_events import (
    DeviceCommandEvent,
    DeviceCreatedEvent,
    DeviceDeletedEvent,
    DeviceUpdatedEvent,
    EventType,
    PowerReadingEvent,
)

logger = logging.getLogger(__name__)


# ============================================================
# MAIN HANDLER
# ============================================================


async def nats_event_handler(msg):
    logger.info("📩 COMMAND RECEIVED | subject=%s", msg.subject)

    try:
        raw = json.loads(msg.data.decode())

        # -------------------------------------------------
        # HEARTBEAT CONTROL
        # -------------------------------------------------
        if msg.subject.endswith(".command.heartbeat"):
            await handle_heartbeat_control(raw)
            return

        # -------------------------------------------------
        # DEVICE EVENTS
        # -------------------------------------------------
        event_type = raw.get("event_type")
        ack_subject = raw.get("ack_subject")

        if not ack_subject:
            logger.error("❌ Missing ack_subject in payload")
            return

        event = parse_device_event(event_type, raw)

        if not event:
            logger.error("❌ Unknown event type: %s", event_type)
            await send_ack(ack_subject, raw.get("device_id"), ok=False)
            return

        ok = await execute_event(event)

        await send_event_ack(event, ack_subject, ok)

    except Exception:
        logger.exception("🔥 Unhandled error while processing command")


# ============================================================
# HEARTBEAT CONTROL
# ============================================================


async def handle_heartbeat_control(payload: dict):
    action = payload.get("action")

    logger.info("💓 HEARTBEAT CONTROL | action=%s", action)

    if action == "START_HEARTBEAT":
        await heartbeat_service.start()

    elif action == "STOP_HEARTBEAT":
        await heartbeat_service.stop()

    else:
        logger.warning("Unknown heartbeat action: %s", action)


# ============================================================
# DEVICE EVENT PARSING
# ============================================================


def parse_device_event(event_type: str, raw: dict):
    match event_type:
        case EventType.DEVICE_CREATED:
            return DeviceCreatedEvent(**raw)

        case EventType.DEVICE_UPDATED:
            return DeviceUpdatedEvent(**raw)

        case EventType.DEVICE_DELETED:
            return DeviceDeletedEvent(**raw)

        case EventType.DEVICE_COMMAND:
            return DeviceCommandEvent(**raw)

        case EventType.CURRENT_ENERGY:
            return PowerReadingEvent(**raw)

        case _:
            return None


# ============================================================
# ACKS
# ============================================================


async def send_event_ack(event, ack_subject: str, ok: bool):
    payload = event.data.model_dump()
    device_id = payload.get("device_id")
    manual_state = payload.get("is_on") or payload.get("manual_state")

    ack_payload = {
        "data": {
            "device_id": device_id,
            "ok": ok,
            **({"manual_state": manual_state} if manual_state is not None else {}),
        }
    }

    await nats_client.publish_raw(ack_subject, ack_payload)

    logger.info("✅ ACK SENT | subject=%s", ack_subject)


async def send_ack(ack_subject: str, device_id: int | None, ok: bool):
    await nats_client.publish_raw(
        ack_subject,
        {
            "data": {
                "device_id": device_id,
                "ok": ok,
            }
        },
    )


# ============================================================
# EXECUTION
# ============================================================


async def execute_event(event) -> bool:
    try:
        result = await event_service.handle_event(event)
        return bool(result) or result is None
    except Exception:
        logger.exception("❌ Error while handling device event")
        return False
