from __future__ import annotations

from tortoise import fields, Model

from piltover.db import models


class StickersetThumb(Model):
    id: int = fields.BigIntField(pk=True)
    set: models.Stickerset = fields.ForeignKeyField("models.Stickerset")
    file: models.File = fields.ForeignKeyField("models.File")
