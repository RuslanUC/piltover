from os import environ
from typing import Literal

from pydantic import BaseModel, Base64Bytes
from pydantic_settings import BaseSettings, SettingsConfigDict, PydanticBaseSettingsSource, TomlConfigSettingsSource


class _DcAddress(BaseModel):
    host: str
    port: int


class _Dc(BaseModel):
    id: int
    addresses: list[_DcAddress]


class _Gifs(BaseModel):
    provider: Literal["tenor", "klipy"]
    api_key: str


class _AppConfig(BaseModel):
    dc_list: list[_Dc]
    this_dc: int
    name: str = "Piltover"
    system_user_username: str = "piltover"

    basic_group_member_limit: int = 50
    super_group_member_limit: int = 1000
    edit_time_limit: int = 48 * 60 * 60
    max_message_length: int = 4096
    max_caption_length: int = 2048
    channels_per_user_limit: int = 100
    public_channels_limit: int = 10
    pinned_dialogs_limit: int = 5
    faved_stickers_limit: int = 15
    saved_gifs_limit: int = 100
    recent_stickers_limit: int = 25
    reactions_unique_max: int = 11
    user_bio_limit: int = 100
    basic_group_admin_limit: int = 10
    channel_admin_limit: int = 25

    hmac_key: Base64Bytes
    file_ref_expire_minutes: int = 60 * 4
    contact_token_expire_seconds: int = 60 * 30
    srp_password_reset_wait_seconds: int = 86400 * 7
    scheduled_instant_send_threshold: int = 30
    account_delete_wait_seconds: int = 86400 * 7
    channel_delete_history_min_id_threshold: int = 1000

    gifs: _Gifs | None = None


class AppConfig(BaseSettings):
    app: _AppConfig

    model_config = SettingsConfigDict(toml_file=environ.get("APP_CONFIG", "config/app.toml"))

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


APP_CONFIG = AppConfig().app

DICE_CONFIG = {
    "\U0001F3B2": (6, 62),  # Die
    "\U0001F3AF": (6, 62),  # Target
    "\U0001F3C0": (5, 110),  # Basketball
    "\u26bd": (5, 110),  # Football
    "\u26bd\ufe0f": (5, 110),  # Football
    "\U0001F3B0": (64, 110),  # Slot machine
    "\U0001F3B3": (6, 110),  # Bowling
}
