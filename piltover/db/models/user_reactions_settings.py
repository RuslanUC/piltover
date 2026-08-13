from __future__ import annotations

from tortoise import Model, fields

from piltover.db import models


class UserReactionsSettings(Model):
    id: int = fields.BigIntField(primary_key=True)
    user: models.User = fields.OneToOneField("models.User")
    default_reaction: models.Reaction | None = fields.ForeignKeyField("models.Reaction", null=True, default=None)
    default_custom_emoji: models.File | None = fields.ForeignKeyField("models.File", null=True, default=None)

    user_id: int
    default_reaction_id: int | None
    default_custom_emoji_id: int | None
