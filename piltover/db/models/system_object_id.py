from __future__ import annotations

from tortoise import Model, fields

from piltover.db import models
from piltover.db.enums import SystemObjectType


class SystemObjectId(Model):
    id: int = fields.BigIntField(pk=True)
    type: SystemObjectType = fields.IntEnumField(SystemObjectType, description="")
    original_id: int = fields.BigIntField()
    checksum: int = fields.BigIntField()
    our_file: models.File | None = fields.ForeignKeyField("models.File", null=True, default=None)
    our_stickerset: models.Stickerset | None = fields.ForeignKeyField("models.Stickerset", null=True, default=None)
    our_emoji_group: models.EmojiGroup | None = fields.ForeignKeyField("models.EmojiGroup", null=True, default=None)

    our_file_id: int | None
    our_stickerset_id: int | None
    our_emoji_group_id: int | None

    class Meta:
        unique_together = (
            ("type", "original_id"),
        )
