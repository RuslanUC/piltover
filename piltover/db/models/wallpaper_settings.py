from __future__ import annotations

from enum import IntEnum

from tortoise import Model, fields

from piltover.db import models
from piltover.tl.types import ThemeSettings as TLThemeSettings, BaseThemeClassic, BaseThemeDay, BaseThemeNight, \
    BaseThemeTinted, BaseThemeArctic, WallPaperSettings
from piltover.tl.base import BaseTheme as TLBaseTheme


class BaseTheme(IntEnum):
    CLASSIC = 1
    DAY = 2
    NIGHT = 3
    TINTED = 4
    ARCTIC = 5

    def to_tl(self) -> TLBaseTheme:
        return {
            BaseTheme.CLASSIC: BaseThemeClassic(),
            BaseTheme.DAY: BaseThemeDay(),
            BaseTheme.NIGHT: BaseThemeNight(),
            BaseTheme.TINTED: BaseThemeTinted(),
            BaseTheme.ARCTIC: BaseThemeArctic(),
        }[self]


class WallpaperSettings(Model):
    id: int = fields.BigIntField(pk=True)
    wallpaper: models.Wallpaper = fields.OneToOneField("models.Wallpaper")
    blur: bool = fields.BooleanField()
    motion: bool = fields.BooleanField()
    background_color: int | None = fields.IntField(null=True)
    second_background_color: int | None = fields.IntField(null=True)
    third_background_color: int | None = fields.IntField(null=True)
    fourth_background_color: int | None = fields.IntField(null=True)
    intensity: int | None = fields.IntField(null=True)
    rotation: int | None = fields.IntField(null=True)
    emoticon: str | None = fields.CharField(max_length=8, null=True)

    wallpaper_id: int

    class Meta:
        unique_together = (
            ("theme", "base_theme"),
        )

    def to_tl(self) -> WallPaperSettings:
        return WallPaperSettings(
            blur=self.blur,
            motion=self.motion,
            background_color=self.background_color,
            second_background_color=self.second_background_color,
            third_background_color=self.third_background_color,
            fourth_background_color=self.fourth_background_color,
            intensity=self.intensity,
            rotation=self.rotation,
            emoticon=self.emoticon,
        )
