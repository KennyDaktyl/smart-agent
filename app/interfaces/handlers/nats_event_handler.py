import asyncio
import json
import logging

from app.application.microcontroller_command_service import (
    microcontroller_command_service,
)
from pydantic import ValidationError

from app.application.event_service import event_service
from app.application.provider_service import ProviderUpdateResult
from app.core.heartbeat_service import HeartbeatPublishTrigger, heartbeat_service
from app.core.nats_client import nats_client
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
from app.domain.events.enums import HeartbeatControlAction, MicrocontrollerCommandType
from app.domain.gpio.runtime_device import RuntimeDevice
from app.infrastructure.config.domain_config_repository import domain_config_repository
from app.infrastructure.gpio.gpio_manager import gpio_manager

logger = logging.getLogger(__name__)

COMMAND_FROM_NATS_GATEWAY = ".command.heartbeat"
UNKNOWN_DEVICE_ID = -1
UNKNOWN_DEVICE_NUMBER = -1


# ============================================================
# MAIN HANDLER
# ============================================================


async def nats_event_handler(msg):
    if msg.subject.endswith(".ack"):
        logger.debug("Ignoring ACK message | subject=%s", msg.subject)
        return

    logger.info("📩 COMMAND RECEIVED | subject=%s", msg.subject)

    ack_subject = None
    device_id = UNKNOWN_DEVICE_ID
    device_number = UNKNOWN_DEVICE_NUMBER
    command_id: str | None = None

    try:
        raw = json.loads(msg.data.decode())

        # -------------------------------------------------
        # HEARTBEAT CONTROL
        # -------------------------------------------------
        if msg.subject.endswith(COMMAND_FROM_NATS_GATEWAY):
            await handle_heartbeat_control(raw)
            return

        # -------------------------------------------------
        # DEVICE EVENTS
        # -------------------------------------------------
        event_type = raw.get("event_type")
        ack_subject = raw.get("ack_subject")

        if not ack_subject:
            logger.error("Missing ack_subject in payload")
            return

        device_id = _extract_device_id(raw)
        device_number = _extract_device_number(raw)
        command_id = _extract_command_id(raw)

        try:
            event = parse_device_event(event_type, raw)
        except ValidationError:
            logger.exception("Invalid device event payload")
            await send_ack(
                ack_subject=ack_subject,
                device_id=device_id,
                device_number=device_number,
                ok=False,
                command_id=command_id,
            )
            return

        if not event:
            logger.error("Unknown event type: %s", event_type)
            await send_ack(
                ack_subject=ack_subject,
                device_id=device_id,
                device_number=device_number,
                ok=False,
                command_id=command_id,
            )
            return

        result = await execute_event(event)

        if isinstance(event, ProviderUpdatedEvent):
            await send_provider_update_ack(
                ack_subject=ack_subject,
                result=result,
            )
            return

        # DEVICE_COMMAND → extended ACK
        if isinstance(event, DeviceCommandEvent):
            logger.info(
                "Device command executed | device_id=%s device_number=%s mode=%s is_on=%s",
                event.data.device_id,
                event.data.device_number,
                event.data.mode,
                event.data.is_on,
            )
            ok = isinstance(result, RuntimeDevice)
            await send_event_ack(
                device=result if ok else None,
                ack_subject=ack_subject,
                ok=ok,
                device_id=device_id,
                device_number=device_number,
                command_id=event.data.command_id or command_id,
            )
            return

        if isinstance(event, MicrocontrollerCommandEvent):
            result_payload = result if isinstance(result, dict) else {}
            ok = bool(result_payload.get("ok"))

            await send_microcontroller_command_ack(
                ack_subject=ack_subject,
                ok=ok,
                command=event.data.command,
                command_id=event.data.command_id or command_id,
                result=result_payload,
            )

            if ok and event.data.command == MicrocontrollerCommandType.REBOOT_AGENT:
                asyncio.create_task(microcontroller_command_service.reboot_after_ack())

            return

        # All other events → simple ACK
        await send_ack(
            ack_subject=ack_subject,
            device_id=device_id,
            device_number=device_number,
            ok=bool(result),
            command_id=command_id,
        )

    except json.JSONDecodeError:
        logger.exception("Invalid JSON command payload")
        if ack_subject:
            await send_ack(
                ack_subject=ack_subject,
                device_id=device_id,
                device_number=device_number,
                ok=False,
                command_id=command_id,
            )
    except Exception:
        logger.exception("🔥 Unhandled error while processing command")
        if ack_subject:
            await send_ack(
                ack_subject=ack_subject,
                device_id=device_id,
                device_number=device_number,
                ok=False,
                command_id=command_id,
            )


# ============================================================
# HELPERS
# ============================================================


def _extract_int(value, fallback: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback


def _extract_device_id(raw: dict) -> int:
    data = raw.get("data")
    if isinstance(data, dict):
        return _extract_int(data.get("device_id"), UNKNOWN_DEVICE_ID)
    return UNKNOWN_DEVICE_ID


def _extract_device_number(raw: dict) -> int:
    data = raw.get("data")
    if isinstance(data, dict):
        return _extract_int(data.get("device_number"), UNKNOWN_DEVICE_NUMBER)
    return UNKNOWN_DEVICE_NUMBER


def _extract_command_id(raw: dict) -> str | None:
    data = raw.get("data")
    if not isinstance(data, dict):
        return None
    value = data.get("command_id")
    if isinstance(value, str):
        normalized = value.strip()
        return normalized or None
    return None


# ============================================================
# HEARTBEAT CONTROL
# ============================================================


async def handle_heartbeat_control(payload: dict):
    raw_action = payload.get("action")
    action = None
    if isinstance(raw_action, str):
        try:
            action = HeartbeatControlAction(raw_action)
        except ValueError:
            action = None

    logger.info("💓 HEARTBEAT CONTROL | action=%s", raw_action)

    if action == HeartbeatControlAction.START_HEARTBEAT:
        await heartbeat_service.start()
        logger.info("Heartbeat started via control command")
    elif action == HeartbeatControlAction.RELOAD_HEARTBEAT:
        published = await heartbeat_service.publish_now(
            trigger=HeartbeatPublishTrigger.RELOAD,
        )
        if published:
            logger.info("Heartbeat reloaded via control command")
        else:
            logger.warning("Heartbeat reload publish failed via control command")
    elif action == HeartbeatControlAction.STOP_HEARTBEAT:
        await heartbeat_service.stop()
        logger.info("Heartbeat stopped via control command")
    else:
        logger.warning("Unknown heartbeat action: %s", raw_action)


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
        case EventType.MICROCONTROLLER_COMMAND:
            return MicrocontrollerCommandEvent(**raw)
        case EventType.CURRENT_ENERGY:
            return PowerReadingEvent(**raw)
        case EventType.PROVIDER_UPDATED:
            return ProviderUpdatedEvent(**raw)
        case _:
            return None


# ============================================================
# ACKS
# ============================================================


async def send_event_ack(
    device: RuntimeDevice | None,
    ack_subject: str,
    ok: bool,
    device_id: int,
    device_number: int,
    command_id: str | None = None,
):
    is_on = gpio_manager.read_is_on_by_number(device_number)
    payload_data = {
        "device_id": device_id,
        "device_number": device_number,
        "ok": ok,
        "is_on": is_on,
    }

    if device:
        is_on = gpio_manager.read_is_on_by_number(device.device_number)
        payload_data["device_id"] = device.device_id
        payload_data["device_number"] = device.device_number
        payload_data["mode"] = (
            device.mode.value if hasattr(device.mode, "value") else str(device.mode)
        )
        payload_data["desired_state"] = device.desired_state
        payload_data["actual_state"] = is_on
        payload_data["is_on"] = is_on
    if command_id:
        payload_data["command_id"] = command_id

    ack_payload = {"data": payload_data}

    await nats_client.publish_raw(ack_subject, ack_payload)

    logger.info("ACK SENT | subject=%s", ack_subject)


async def send_ack(
    ack_subject: str,
    device_id: int,
    device_number: int,
    ok: bool,
    command_id: str | None = None,
):
    is_on = gpio_manager.read_is_on_by_number(device_number)
    payload_data = {
        "device_id": device_id,
        "device_number": device_number,
        "ok": ok,
        "is_on": is_on,
    }
    if command_id:
        payload_data["command_id"] = command_id
    ack_payload = {"data": payload_data}

    await nats_client.publish_raw(ack_subject, ack_payload)

    logger.info("ACK SENT | subject=%s", ack_subject)


async def send_provider_update_ack(
    ack_subject: str,
    result: object,
):
    microcontroller_uuid = ""
    previous_provider_uuid = ""
    provider_uuid = ""
    changed = False
    ok = False

    if isinstance(result, ProviderUpdateResult):
        ok = result.ok
        changed = result.changed
        microcontroller_uuid = result.microcontroller_uuid
        previous_provider_uuid = result.previous_provider_uuid
        provider_uuid = result.provider_uuid
    else:
        ok = bool(result)
        try:
            config = domain_config_repository.load()
            microcontroller_uuid = config.microcontroller_uuid
            provider_uuid = config.provider_uuid
            previous_provider_uuid = config.provider_uuid
        except Exception:
            logger.exception("Failed to load config for provider update ACK")

    ack_payload = {
        "data": {
            "ok": ok,
            "changed": changed,
            "microcontroller_uuid": microcontroller_uuid,
            "previous_provider_uuid": previous_provider_uuid,
            "provider_uuid": provider_uuid,
        }
    }

    await nats_client.publish_raw(ack_subject, ack_payload)

    logger.info("ACK SENT | subject=%s", ack_subject)


async def send_microcontroller_command_ack(
    ack_subject: str,
    ok: bool,
    command: MicrocontrollerCommandType,
    command_id: str | None,
    result: dict,
):
    payload_data = {
        "ok": ok,
        "command": command.value,
    }

    if command_id:
        payload_data["command_id"] = command_id

    message = result.get("message")
    if isinstance(message, str) and message:
        payload_data["message"] = message

    config_json = result.get("config_json")
    if isinstance(config_json, dict):
        payload_data["config_json"] = config_json

    hardware_config_json = result.get("hardware_config_json")
    if isinstance(hardware_config_json, dict):
        payload_data["hardware_config_json"] = hardware_config_json

    ack_payload = {"data": payload_data}
    await nats_client.publish_raw(ack_subject, ack_payload)
    logger.info("ACK SENT | subject=%s", ack_subject)


# ============================================================
# EXECUTION
# ============================================================


async def execute_event(event):
    try:
        return await event_service.handle_event(event)
    except Exception:
        logger.exception("Error while handling device event")
        return False
