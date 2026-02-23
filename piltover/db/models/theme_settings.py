from __future__ import annotations

from enum import IntEnum

from tortoise import Model, fields

from piltover.db import models
from piltover.tl.types import ThemeSettings as TLThemeSettings, BaseThemeClassic, BaseThemeDay, BaseThemeNight, \
    BaseThemeTinted, BaseThemeArctic
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

    @classmethod
    def from_tl(cls, tl: TLBaseTheme) -> BaseTheme:
        return {
            BaseThemeClassic: BaseTheme.CLASSIC,
            BaseThemeDay: BaseTheme.DAY,
            BaseThemeNight: BaseTheme.NIGHT,
            BaseThemeTinted: BaseTheme.TINTED,
            BaseThemeArctic: BaseTheme.ARCTIC,
        }[type(tl)]


class ThemeSettings(Model):
    id: int = fields.BigIntField(pk=True)
    theme: models.Theme = fields.ForeignKeyField("models.Theme")
    base_theme: BaseTheme = fields.IntEnumField(BaseTheme, description="")
    accent_color: int = fields.IntField()
    outbox_accent_color: int | None = fields.IntField(null=True)
    message_colors_animated: bool = fields.BooleanField()
    message_color_1: int | None = fields.IntField(null=True)
    message_color_2: int | None = fields.IntField(null=True)
    message_color_3: int | None = fields.IntField(null=True)
    message_color_4: int | None = fields.IntField(null=True)
    wallpaper: models.Wallpaper | None = fields.ForeignKeyField("models.Wallpaper")

    theme_id: int
    wallpaper_id: int | None

    class Meta:
        unique_together = (
            ("theme", "base_theme"),
        )

    def to_tl(self) -> TLThemeSettings:
        message_colors = None if self.message_color_1 is None else [self.message_color_1]
        if self.message_color_2 is not None:
            message_colors.append(self.message_color_2)
        if self.message_color_3 is not None:
            message_colors.append(self.message_color_3)
        if self.message_color_4 is not None:
            message_colors.append(self.message_color_4)

        return TLThemeSettings(
            message_colors_animated=self.message_colors_animated,
            base_theme=self.base_theme.to_tl(),
            accent_color=self.accent_color,
            outbox_accent_color=self.outbox_accent_color,
            message_colors=message_colors,
            wallpaper=self.wallpaper.to_tl() if self.wallpaper is not None else None,
        )
