from __future__ import annotations

from tortoise import Model, fields

from piltover.db import models


class ChatWallpaper(Model):
    id: int = fields.BigIntField(pk=True)
    user: models.User = fields.ForeignKeyField("models.User", related_name="wallpaper_user")
    target: models.User = fields.ForeignKeyField("models.User", related_name="wallpaper_target")
    wallpaper: models.Wallpaper = fields.ForeignKeyField("models.Wallpaper")
    overridden: bool = fields.BooleanField(default=False)

    user_id: int
    target_id: int
    wallpaper_id: int
