from os import environ
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict, PydanticBaseSettingsSource, TomlConfigSettingsSource


class _CacheConfig(BaseModel):
    backend: Literal["memory", "redis", "memcached", "none"] = "memory"
    endpoint: str | None = None
    port: int | None = None
    db: str | None = None


class _TracingConfig(BaseModel):
    backend: Literal["console", "zipkin", "noop"] = "noop"
    zipkin_address: str | None = None


class _TelegramIntegration(BaseModel):
    # TODO: add "telethon" backend?

    enabled: bool = False
    bot_token: str | None = None
    max_accounts_per_user: int = 3
    phone_number_policy: Literal["real", "random", "user-provided"] = "random"


class _System(BaseModel):
    data_dir: Path = Path("data")
    database_connection_string: str = "sqlite://data/secrets/piltover.db"
    rabbitmq_address: str | None = None
    redis_address: str | None = None
    cache: _CacheConfig
    debug_tracing: _TracingConfig
    debug_enable_aiomonitor: bool = False
    enable_system_bot: bool = False
    telegram_integration: _TelegramIntegration


class SystemConfig(BaseSettings):
    system: _System = Field(init=False)

    model_config = SettingsConfigDict(toml_file=environ.get("SYSTEM_CONFIG", "config/system.toml"))

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        return TomlConfigSettingsSource(settings_cls),


SYSTEM_CONFIG = SystemConfig().system
