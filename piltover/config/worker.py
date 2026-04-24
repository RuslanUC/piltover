import os
from pathlib import Path
from typing import Self

from pydantic import BaseModel, model_validator, Field
from pydantic_settings import BaseSettings, SettingsConfigDict, PydanticBaseSettingsSource, TomlConfigSettingsSource

_ENV_VAR = "WORKER_CONFIG"


class _Worker(BaseModel):
    pubkey_file: Path | None = None

    @model_validator(mode="after")
    def set_default_keys(self) -> Self:
        from .system import SYSTEM_CONFIG

        if self.pubkey_file is None:
            self.pubkey_file = SYSTEM_CONFIG.data_dir / "secrets/pubkey.asc"
        return self


class WorkerConfig(BaseSettings):
    worker: _Worker = Field(init=False)

    model_config = SettingsConfigDict(toml_file=os.environ.get(_ENV_VAR, "config/worker.toml"))

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


if _ENV_VAR in os.environ:
    WORKER_CONFIG = WorkerConfig().worker
else:
    WORKER_CONFIG = None
