from __future__ import annotations

from tortoise import fields, Model

from piltover.db import models


class StickersetThumb(Model):
    id: int = fields.BigIntField(primary_key=True)
    set: models.Stickerset = fields.OneToOneField("models.Stickerset", related_name="thumb")
    file: models.File = fields.ForeignKeyField("models.File")

    set_id: int
    file_id: int
