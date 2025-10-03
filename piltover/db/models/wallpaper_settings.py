from __future__ import annotations

from enum import IntEnum

from tortoise import Model, fields

from piltover.db import models
from piltover.tl.base import BaseTheme as TLBaseTheme
from piltover.tl.types import BaseThemeClassic, BaseThemeDay, BaseThemeNight, \
    BaseThemeTinted, BaseThemeArctic, WallPaperSettings


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


# TODO: just merge all the fields into models.Wallpaper model ?
class WallpaperSettings(Model):
    id: int = fields.BigIntField(pk=True)
    wallpaper: models.Wallpaper = fields.OneToOneField("models.Wallpaper")
    blur: bool = fields.BooleanField(default=False)
    motion: bool = fields.BooleanField(default=False)
    background_color: int | None = fields.IntField(null=True, default=None)
    second_background_color: int | None = fields.IntField(null=True, default=None)
    third_background_color: int | None = fields.IntField(null=True, default=None)
    fourth_background_color: int | None = fields.IntField(null=True, default=None)
    intensity: int | None = fields.IntField(null=True, default=None)
    rotation: int | None = fields.IntField(null=True, default=None)
    emoticon: str | None = fields.CharField(max_length=8, null=True, default=None)

    wallpaper_id: int

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
