import asyncio

from app.application.device_factory import merge_configs
from app.core.logging_config import logger
from app.core.nats_subjects import NatsSubjects
from app.core.heartbeat_service import heartbeat_service

from app.core.nats_client import nats_client

from app.infrastructure.config.domain_config_repository import (
    domain_config_repository,
)
from app.infrastructure.config.hardware_config_repository import (
    hardware_config_repository,
)

from app.infrastructure.gpio.gpio_manager import gpio_manager

from app.interfaces.handlers.nats_event_handler import nats_event_handler
from app.interfaces.handlers.power_reading_handler import (
    inverter_production_handler,
)


async def bootstrap_gpio():
    domain_config = domain_config_repository.load()
    hardware_config = hardware_config_repository.load()

    merged_devices = merge_configs(
        domain_config,
        hardware_config,
    )

    gpio_manager.load_devices(merged_devices)

    return domain_config


async def setup_nats(domain_config):
    await nats_client.connect()

    # -------------------------------------------------
    # Provider energy
    # -------------------------------------------------
    provider_subject = NatsSubjects.provider_event(
        domain_config.provider_uuid,
        "provider_current_energy",
    )

    await nats_client.subscribe(
        provider_subject,
        inverter_production_handler,
    )

    logger.info(f"Subscribed: {provider_subject}")

    # -------------------------------------------------
    # All agent commands (including heartbeat)
    # -------------------------------------------------
    agent_subject = NatsSubjects.agent_command(
        domain_config.microcontroller_uuid,
        ">",
    )

    await nats_client.subscribe(
        agent_subject,
        nats_event_handler,
    )

    logger.info(f"Subscribed: {agent_subject}")


async def main():
    try:
        logger.info("🚀 Starting Smart Energy Agent")

        domain_config = await bootstrap_gpio()

        await setup_nats(domain_config)

        await asyncio.Event().wait()

    except asyncio.CancelledError:
        logger.info("Shutdown signal received.")

    except Exception:
        logger.exception("Fatal error in main loop")

    finally:
        logger.info("Stopping heartbeat...")
        await heartbeat_service.stop()

        logger.info("Closing NATS connection...")
        try:
            await nats_client.close()
        except Exception:
            pass

        logger.info("Agent stopped.")


if __name__ == "__main__":
    asyncio.run(main())
