from __future__ import annotations

from tortoise import Model, fields

from piltover.db import models
from piltover.tl.types import BotCommand as TLBotCommand


class BotCommand(Model):
    id: int = fields.BigIntField(pk=True)
    bot: models.User = fields.ForeignKeyField("models.User")
    name: str = fields.CharField(max_length=32)
    description: str = fields.CharField(max_length=240)

    bot_id: int

    def to_tl(self) -> TLBotCommand:
        return TLBotCommand(
            command=self.name,
            description=self.description,
        )
