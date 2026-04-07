import os
from pathlib import Path
from typing import Self

from pydantic import BaseModel, model_validator, Base64Bytes
from pydantic_settings import BaseSettings, SettingsConfigDict, PydanticBaseSettingsSource, TomlConfigSettingsSource

_ENV_VAR = "GATEWAY_CONFIG"


class _Gateway(BaseModel):
    host: str = "127.0.0.1"
    port: int = 4430
    privkey_file: Path | None = None
    pubkey_file: Path | None = None
    salt_key: Base64Bytes

    @model_validator(mode="after")
    def set_default_keys(self) -> Self:
        from .system import SYSTEM_CONFIG

        if self.privkey_file is None:
            self.privkey_file = SYSTEM_CONFIG.data_dir / "secrets/privkey.asc"
        if self.pubkey_file is None:
            self.pubkey_file = SYSTEM_CONFIG.data_dir / "secrets/pubkey.asc"
        return self


class GatewayConfig(BaseSettings):
    gateway: _Gateway

    model_config = SettingsConfigDict(toml_file=os.environ.get(_ENV_VAR, "config/gateway.toml"))

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
    GATEWAY_CONFIG = GatewayConfig().gateway
else:
    GATEWAY_CONFIG = None
