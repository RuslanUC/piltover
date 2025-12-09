from __future__ import annotations

from tortoise import Model, fields

from piltover.db import models


class UserBackgroundEmojis(Model):
    id: int = fields.BigIntField(pk=True)
    user: models.User = fields.OneToOneField("models.User")
    accent_emoji: models.File | None = fields.ForeignKeyField("models.File", null=True, default=None, related_name="accent_emoji")
    profile_emoji: models.File | None = fields.ForeignKeyField("models.File", null=True, default=None, related_name="profile_emoji")

    accent_emoji_id: int | None
    profile_emoji_id: int | None
