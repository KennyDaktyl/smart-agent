from app.core.config import settings


class NatsScopes:
    PROVIDER = "provider"
    AGENT = "agent"


class NatsChannels:
    EVENT = "event"
    COMMAND = "command"


class ProviderEvents:
    CURRENT_ENERGY = "provider_current_energy"


class AgentEvents:
    HEARTBEAT = "heartbeat"
    STATUS = "status"


class AgentCommands:
    UPDATE_CONFIG = "update_config"
    RESTART = "restart"
    START_HEARTBEAT = "start_heartbeat"
    STOP_HEARTBEAT = "stop_heartbeat"


class NatsSubjects:

    @staticmethod
    def provider_event(provider_uuid: str, event: str) -> str:
        return (
            f"{settings.NATS_PREFIX}."
            f"{provider_uuid}."
            f"{NatsChannels.EVENT}."
            f"{event}"
        )

    @staticmethod
    def agent_event(micro_uuid: str, event: str) -> str:
        return (
            f"{settings.NATS_PREFIX}."
            f"{micro_uuid}."
            f"{NatsChannels.EVENT}."
            f"microcontroller_{event}"
        )

    @staticmethod
    def agent_command(micro_uuid: str, command: str) -> str:
        return (
            f"{settings.NATS_PREFIX}."
            f"{micro_uuid}."
            f"{NatsChannels.COMMAND}."
            f"{command}"
        )
