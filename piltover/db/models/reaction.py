from __future__ import annotations

from tortoise import Model, fields

from piltover.db import models


class Reaction(Model):
    id: int = fields.BigIntField(pk=True)
    reaction: str = fields.CharField(max_length=8)
    title: str = fields.CharField(max_length=64)
    static_icon: models.File = fields.ForeignKeyField("models.File")
    appear_animation: models.File = fields.ForeignKeyField("models.File")
    select_animation: models.File = fields.ForeignKeyField("models.File")
    activate_animation: models.File = fields.ForeignKeyField("models.File")
    effect_animation: models.File = fields.ForeignKeyField("models.File")
    around_animation: models.File | None = fields.ForeignKeyField("models.File", null=True, default=None)
    center_icon: models.File | None = fields.ForeignKeyField("models.File", null=True, default=None)
