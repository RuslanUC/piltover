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
    async def get_ids_for_message(cls, message: models.MessageContent) -> tuple[set[int], set[int], set[int]]:
        user_ids = set()
        chat_ids = set()
        channel_ids = set()

        related = await cls.filter(message=message).values_list("user_id", "chat_id", "channel_id")
        for user_id, chat_id, channel_id in related:
            if user_id is not None:
                user_ids.add(user_id)
            if chat_id is not None:
                chat_ids.add(chat_id)
            if channel_id is not None:
                channel_ids.add(channel_id)

        return user_ids, chat_ids, channel_ids

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
