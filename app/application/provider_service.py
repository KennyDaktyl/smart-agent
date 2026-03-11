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
    previous_unit: str | None
    unit: str | None
    has_power_meter: bool
    has_energy_storage: bool


class ProviderService:
    async def update_provider_uuid(
        self,
        provider_uuid: str,
        unit: str | None = None,
        has_power_meter: bool | None = None,
        has_energy_storage: bool | None = None,
    ) -> ProviderUpdateResult:
        normalized_provider_uuid = provider_uuid.strip()
        if not normalized_provider_uuid:
            raise ValueError("provider_uuid must not be empty")
        normalized_unit = unit.strip() if isinstance(unit, str) else None
        if normalized_unit == "":
            normalized_unit = None

        config = domain_config_repository.load()
        previous_provider_uuid = config.provider_uuid
        microcontroller_uuid = config.microcontroller_uuid
        previous_unit = config.unit
        normalized_has_power_meter = bool(
            config.provider_has_power_meter
            if has_power_meter is None
            else has_power_meter
        )
        normalized_has_energy_storage = bool(
            config.provider_has_energy_storage
            if has_energy_storage is None
            else has_energy_storage
        )

        if (
            normalized_provider_uuid == previous_provider_uuid
            and normalized_unit == previous_unit
            and normalized_has_power_meter == config.provider_has_power_meter
            and normalized_has_energy_storage == config.provider_has_energy_storage
        ):
            logger.info(
                "Provider config already set: provider_uuid=%s unit=%s "
                "has_power_meter=%s has_energy_storage=%s",
                normalized_provider_uuid,
                normalized_unit,
                normalized_has_power_meter,
                normalized_has_energy_storage,
            )
            return ProviderUpdateResult(
                ok=True,
                changed=False,
                microcontroller_uuid=microcontroller_uuid,
                previous_provider_uuid=previous_provider_uuid,
                provider_uuid=normalized_provider_uuid,
                previous_unit=previous_unit,
                unit=normalized_unit,
                has_power_meter=normalized_has_power_meter,
                has_energy_storage=normalized_has_energy_storage,
            )

        await provider_subscription_service.switch_provider_uuid(normalized_provider_uuid)
        try:
            domain_config_repository.update(
                provider_uuid=normalized_provider_uuid,
                unit=normalized_unit,
                provider_has_power_meter=normalized_has_power_meter,
                provider_has_energy_storage=normalized_has_energy_storage,
            )
        except Exception:
            logger.exception(
                "Failed to persist provider config in agent config. "
                "provider_uuid=%s unit=%s. Rolling back subscription.",
                normalized_provider_uuid,
                normalized_unit,
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
            "Provider config updated | previous_uuid=%s current_uuid=%s "
            "previous_unit=%s current_unit=%s has_power_meter=%s "
            "has_energy_storage=%s",
            previous_provider_uuid,
            normalized_provider_uuid,
            previous_unit,
            normalized_unit,
            normalized_has_power_meter,
            normalized_has_energy_storage,
        )
        return ProviderUpdateResult(
            ok=True,
            changed=True,
            microcontroller_uuid=microcontroller_uuid,
            previous_provider_uuid=previous_provider_uuid,
            provider_uuid=normalized_provider_uuid,
            previous_unit=previous_unit,
            unit=normalized_unit,
            has_power_meter=normalized_has_power_meter,
            has_energy_storage=normalized_has_energy_storage,
        )


provider_service = ProviderService()
