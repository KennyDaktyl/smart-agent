import asyncio
import logging
from dataclasses import dataclass
from typing import Awaitable, Callable, Optional

from app.core.nats_client import nats_client
from app.core.nats_subjects import NatsSubjects, ProviderEvents

logger = logging.getLogger(__name__)

NatsMessageHandler = Callable[[object], Awaitable[None]]


@dataclass
class ProviderSubscriptionSwitchResult:
    previous_provider_uuid: Optional[str]
    provider_uuid: str
    changed: bool


class ProviderSubscriptionService:
    def __init__(self):
        self._provider_subscription = None
        self._provider_uuid: Optional[str] = None
        self._handler: Optional[NatsMessageHandler] = None
        self._lock = asyncio.Lock()

    @staticmethod
    def _subject(provider_uuid: str) -> str:
        return NatsSubjects.provider_event(
            provider_uuid,
            ProviderEvents.CURRENT_ENERGY,
        )

    @staticmethod
    def _normalize_provider_uuid(provider_uuid: str) -> str:
        normalized = provider_uuid.strip()
        if not normalized:
            raise ValueError("provider_uuid must not be empty")
        return normalized

    async def start(self, *, provider_uuid: str, handler: NatsMessageHandler) -> str:
        normalized = self._normalize_provider_uuid(provider_uuid)
        async with self._lock:
            self._handler = handler
            self._provider_subscription = await nats_client.subscribe(
                self._subject(normalized),
                handler,
            )
            self._provider_uuid = normalized
            logger.info("Subscribed provider subject: %s", self._subject(normalized))
            return self._subject(normalized)

    async def switch_provider_uuid(
        self, provider_uuid: str
    ) -> ProviderSubscriptionSwitchResult:
        normalized = self._normalize_provider_uuid(provider_uuid)
        async with self._lock:
            if self._handler is None:
                raise RuntimeError(
                    "Provider subscription handler is not initialized. Call start() first."
                )

            previous_provider_uuid = self._provider_uuid
            if (
                previous_provider_uuid == normalized
                and self._provider_subscription is not None
            ):
                return ProviderSubscriptionSwitchResult(
                    previous_provider_uuid=previous_provider_uuid,
                    provider_uuid=normalized,
                    changed=False,
                )

            previous_subject = (
                self._subject(previous_provider_uuid)
                if previous_provider_uuid is not None
                else None
            )
            previous_subscription = self._provider_subscription

            if previous_subscription is not None:
                try:
                    await previous_subscription.unsubscribe()
                    logger.info("Unsubscribed provider subject: %s", previous_subject)
                except Exception:
                    logger.exception(
                        "Failed to unsubscribe previous provider subject: %s",
                        previous_subject,
                    )

            self._provider_subscription = None
            self._provider_uuid = None

            new_subject = self._subject(normalized)
            try:
                self._provider_subscription = await nats_client.subscribe(
                    new_subject,
                    self._handler,
                )
                self._provider_uuid = normalized
                logger.info("Subscribed provider subject: %s", new_subject)
            except Exception:
                logger.exception(
                    "Failed to subscribe provider subject: %s",
                    new_subject,
                )

                if previous_provider_uuid is not None and previous_subject is not None:
                    try:
                        self._provider_subscription = await nats_client.subscribe(
                            previous_subject,
                            self._handler,
                        )
                        self._provider_uuid = previous_provider_uuid
                        logger.info(
                            "Rollback: re-subscribed previous provider subject: %s",
                            previous_subject,
                        )
                    except Exception:
                        logger.exception(
                            "Rollback failed for previous provider subject: %s",
                            previous_subject,
                        )
                raise

            return ProviderSubscriptionSwitchResult(
                previous_provider_uuid=previous_provider_uuid,
                provider_uuid=normalized,
                changed=True,
            )

    async def stop(self) -> None:
        async with self._lock:
            if self._provider_subscription is None:
                return

            subject = (
                self._subject(self._provider_uuid)
                if self._provider_uuid is not None
                else "<unknown>"
            )
            try:
                await self._provider_subscription.unsubscribe()
                logger.info("Unsubscribed provider subject: %s", subject)
            except Exception:
                logger.exception("Failed to unsubscribe provider subject: %s", subject)
            finally:
                self._provider_subscription = None
                self._provider_uuid = None


provider_subscription_service = ProviderSubscriptionService()
