from os import environ
from pathlib import Path
from typing import Literal

from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict, PydanticBaseSettingsSource, TomlConfigSettingsSource


class _CacheConfig(BaseModel):
    backend: Literal["memory", "redis", "memcached"] = "memory"
    endpoint: str | None = None
    port: int | None = None
    db: str | None = None


class _TracingConfig(BaseModel):
    backend: Literal["console", "zipkin"] = "console"
    zipkin_address: str | None = None


class _System(BaseModel):
    data_dir: Path = Path("data")
    database_connection_string: str = "sqlite://data/secrets/piltover.db"
    rabbitmq_address: str | None = None
    redis_address: str | None = None
    cache: _CacheConfig
    debug_tracing: _TracingConfig


class SystemConfig(BaseSettings):
    system: _System

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
