from __future__ import annotations

from typing import Iterable

from tortoise import Model, fields

from piltover.db import models


class MessageRelated(Model):
    id: int = fields.BigIntField(primary_key=True)
    message: models.MessageContent = fields.ForeignKeyField("models.MessageContent")
    user: models.User | None = fields.ForeignKeyField("models.User", null=True, default=None)
    chat: models.Chat | None = fields.ForeignKeyField("models.Chat", null=True, default=None)
    channel: models.Channel | None = fields.ForeignKeyField("models.Channel", null=True, default=None)

    message_id: int
    user_id: int | None
    chat_id: int | None
    channel_id: int | None

    @classmethod
    async def get_for_message(
            cls, message: models.MessageContent,
    ) -> tuple[Iterable[int], Iterable[int], Iterable[int]]:
        users = set()
        chats = set()
        channels = set()

        for related in await cls.filter(message=message):
            if related.user_id is not None:
                users.add(related.user_id)
            if related.chat_id is not None:
                chats.add(related.chat_id)
            if related.channel_id is not None:
                channels.add(related.channel_id)

        return users, chats, channels
