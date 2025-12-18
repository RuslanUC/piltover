from __future__ import annotations

from tortoise import Model, fields

from piltover.db import models


class GifBotFile(Model):
    id: int = fields.BigIntField(pk=True)
    tenor_id: str = fields.CharField(max_length=32, unique=True)
    file: models.File = fields.ForeignKeyField("models.File")
