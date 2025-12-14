from __future__ import annotations

from typing import Iterable

from tortoise import Model, fields

from piltover.db import models


class MessageRelated(Model):
    id: int = fields.BigIntField(pk=True)
    message: models.Message = fields.ForeignKeyField("models.Message")
    user: models.User | None = fields.ForeignKeyField("models.User", null=True, default=None)
    chat: models.Chat | None = fields.ForeignKeyField("models.Chat", null=True, default=None)
    channel: models.Channel | None = fields.ForeignKeyField("models.Channel", null=True, default=None)

    message_id: int
    user_id: int | None
    chat_id: int | None
    channel_id: int | None

    @classmethod
    async def get_ids_for_message(cls, message: models.Message) -> tuple[set[int], set[int], set[int]]:
        user_ids = set()
        chat_ids = set()
        channel_ids = set()

        related = await cls.filter(message=message).values_list("user__id", "chat__id", "channel__id")
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
            cls, message: models.Message,
    ) -> tuple[Iterable[models.User], Iterable[models.Chat], Iterable[models.Channel]]:
        users = {}
        chats = {}
        channels = {}

        for related in await cls.filter(message=message).select_related("user", "chat", "channel"):
            if related.user_id is not None:
                users[related.user_id] = related.user
            if related.chat_id is not None:
                chats[related.chat_id] = related.chat
            if related.channel_id is not None:
                channels[related.channel_id] = related.channel

        return users.values(), chats.values(), channels.values()
