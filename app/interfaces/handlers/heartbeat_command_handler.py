import json
import logging

from app.core.heartbeat_service import HeartbeatPublishTrigger, heartbeat_service
from app.domain.events.enums import HeartbeatControlAction

logger = logging.getLogger(__name__)


async def handle_heartbeat_command(msg):

    try:
        payload = json.loads(msg.data.decode())

        raw_action = payload.get("action")
        action = None
        if isinstance(raw_action, str):
            try:
                action = HeartbeatControlAction(raw_action)
            except ValueError:
                action = None

        logger.info(
            "HEARTBEAT CONTROL RECEIVED | subject=%s action=%s",
            msg.subject,
            raw_action,
        )

        match action:
            case HeartbeatControlAction.START_HEARTBEAT:
                await heartbeat_service.start()
                logger.info("Heartbeat started via control command")

            case HeartbeatControlAction.RELOAD_HEARTBEAT:
                published = await heartbeat_service.publish_now(
                    trigger=HeartbeatPublishTrigger.RELOAD,
                )
                if published:
                    logger.info("Heartbeat reloaded via control command")
                else:
                    logger.warning("Heartbeat reload publish failed via control command")

            case HeartbeatControlAction.STOP_HEARTBEAT:
                await heartbeat_service.stop()
                logger.info("Heartbeat stopped via control command")

            case _:
                logger.warning(
                    "Unknown heartbeat control action: %s",
                    raw_action,
                )

    except Exception:
        logger.exception("Error handling heartbeat control command")
