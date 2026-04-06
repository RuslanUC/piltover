from os import environ
from pathlib import Path
from typing import Self

from pydantic import BaseModel, model_validator, Base64Bytes
from pydantic_settings import BaseSettings, SettingsConfigDict, PydanticBaseSettingsSource, TomlConfigSettingsSource


class _Worker(BaseModel):
    pubkey_file: Path | None = None

    @model_validator(mode="after")
    def set_default_keys(self) -> Self:
        from .system import SYSTEM_CONFIG

        if self.pubkey_file is None:
            self.pubkey_file = SYSTEM_CONFIG.data_dir / "secrets/pubkey.asc"
        return self


class WorkerConfig(BaseSettings):
    worker: _Worker

    model_config = SettingsConfigDict(toml_file=environ.get("WORKER_CONFIG", "config/worker.toml"))

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


WORKER_CONFIG = WorkerConfig().worker
