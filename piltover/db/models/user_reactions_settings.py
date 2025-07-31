from __future__ import annotations

from tortoise import Model, fields

from piltover.db import models


class UserReactionsSettings(Model):
    id: int = fields.BigIntField(pk=True)
    user: models.User = fields.ForeignKeyField("models.User", unique=True)
    default_reaction: models.Reaction | None = fields.ForeignKeyField("models.Reaction", null=True, default=None)

    default_reaction_id: int | None
