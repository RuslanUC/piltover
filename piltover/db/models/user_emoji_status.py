from __future__ import annotations

from datetime import datetime, UTC

from tortoise import Model, fields

from piltover.db import models
from piltover.tl import EmojiStatus, EmojiStatusEmpty


class UserEmojiStatus(Model):
    id: int = fields.BigIntField(pk=True)
    user: models.User = fields.OneToOneField("models.User")
    emoji: models.File = fields.ForeignKeyField("models.File")
    until: datetime | None = fields.DatetimeField(null=True, default=None)

    user_id: int
    emoji_id: int

    def to_tl(self) -> EmojiStatus | EmojiStatusEmpty:
        if self.until is not None and datetime.now(UTC) > self.until:
            return EmojiStatusEmpty()

        return EmojiStatus(
            document_id=self.emoji_id,
            until=int(self.until.timestamp()) if self.until is not None else None,
        )
