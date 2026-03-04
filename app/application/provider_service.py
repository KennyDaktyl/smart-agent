import logging
from dataclasses import dataclass

from app.core.provider_subscription_service import provider_subscription_service
from app.infrastructure.config.domain_config_repository import domain_config_repository

logger = logging.getLogger(__name__)


@dataclass
class ProviderUpdateResult:
    ok: bool
    changed: bool
    microcontroller_uuid: str
    previous_provider_uuid: str
    provider_uuid: str


class ProviderService:
    async def update_provider_uuid(self, provider_uuid: str) -> ProviderUpdateResult:
        normalized_provider_uuid = provider_uuid.strip()
        if not normalized_provider_uuid:
            raise ValueError("provider_uuid must not be empty")

        config = domain_config_repository.load()
        previous_provider_uuid = config.provider_uuid
        microcontroller_uuid = config.microcontroller_uuid

        if normalized_provider_uuid == previous_provider_uuid:
            logger.info(
                "Provider UUID already set: %s",
                normalized_provider_uuid,
            )
            return ProviderUpdateResult(
                ok=True,
                changed=False,
                microcontroller_uuid=microcontroller_uuid,
                previous_provider_uuid=previous_provider_uuid,
                provider_uuid=normalized_provider_uuid,
            )

        await provider_subscription_service.switch_provider_uuid(normalized_provider_uuid)
        try:
            domain_config_repository.update(provider_uuid=normalized_provider_uuid)
        except Exception:
            logger.exception(
                "Failed to persist provider_uuid=%s in config. Rolling back subscription.",
                normalized_provider_uuid,
            )
            try:
                await provider_subscription_service.switch_provider_uuid(
                    previous_provider_uuid
                )
            except Exception:
                logger.exception(
                    "Rollback failed for provider_uuid=%s",
                    previous_provider_uuid,
                )
            raise

        logger.info(
            "Provider UUID updated | previous=%s current=%s",
            previous_provider_uuid,
            normalized_provider_uuid,
        )
        return ProviderUpdateResult(
            ok=True,
            changed=True,
            microcontroller_uuid=microcontroller_uuid,
            previous_provider_uuid=previous_provider_uuid,
            provider_uuid=normalized_provider_uuid,
        )


provider_service = ProviderService()
