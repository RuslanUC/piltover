from __future__ import annotations

from tortoise import Model, fields

from piltover.db import models


class InstalledWallpaper(Model):
    id: int = fields.BigIntField(pk=True)
    user: models.User = fields.ForeignKeyField("models.User")
    wallpaper: models.Wallpaper = fields.ForeignKeyField("models.Wallpaper")
    settings: models.WallpaperSettings = fields.ForeignKeyField("models.WallpaperSettings")

    user_id: int
    wallpaper_id: int
    settings_id: int

    class Meta:
        unique_together = (
            ("user", "wallpaper",),
        )
