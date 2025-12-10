from __future__ import annotations

from tortoise import Model, fields

from piltover.db import models
from piltover.tl.types import BotInfo as TLBotInfo


class BotInfo(Model):
    id: int = fields.BigIntField(pk=True)
    user: models.User = fields.OneToOneField("models.User")
    description: str | None = fields.CharField(max_length=128, null=True, default=None)
    description_photo: models.File | None = fields.ForeignKeyField("models.File", null=True, default=None)
    # TODO: description_document
    privacy_policy_url: str | None = fields.CharField(max_length=240, null=True, default=None)
    version: int = fields.IntField(default=1)

    user_id: int

    def to_tl(self) -> TLBotInfo:
        return TLBotInfo(
            user_id=self.user_id,
            description=self.description,
            description_photo=self.description_photo.to_tl_photo() if self.description_photo is not None else None,
            commands=[],
            privacy_policy_url=self.privacy_policy_url,
        )
