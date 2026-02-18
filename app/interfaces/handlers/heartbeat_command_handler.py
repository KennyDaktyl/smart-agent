import json
import logging

from app.core.heartbeat_service import heartbeat_service

logger = logging.getLogger(__name__)


class HeartbeatControlActions:
    START = "START_HEARTBEAT"
    STOP = "STOP_HEARTBEAT"


async def handle_heartbeat_command(msg):

    try:
        payload = json.loads(msg.data.decode())

        action = payload.get("action")

        logger.info(
            "HEARTBEAT CONTROL RECEIVED | subject=%s action=%s",
            msg.subject,
            action,
        )

        match action:
            case HeartbeatControlActions.START:
                await heartbeat_service.start()
                logger.info("Heartbeat started via control command")

            case HeartbeatControlActions.STOP:
                await heartbeat_service.stop()
                logger.info("Heartbeat stopped via control command")

            case _:
                logger.warning(
                    "Unknown heartbeat control action: %s",
                    action,
                )

    except Exception:
        logger.exception("Error handling heartbeat control command")
