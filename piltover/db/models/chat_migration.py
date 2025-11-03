from __future__ import annotations

from tortoise import fields, Model

from piltover.db import models


class ChatMigration(Model):
    id: int = fields.BigIntField(pk=True)
    from_chat: models.Chat = fields.OneToOneField("models.Chat")
    to_channel: models.Channel = fields.OneToOneField("models.Channel")
