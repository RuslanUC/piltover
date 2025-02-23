from __future__ import annotations

from contextlib import asynccontextmanager
from enum import IntFlag
from typing import Any, TypeVar, Protocol

import tortoise
from loguru import logger
from tortoise.expressions import Q

from piltover.db import models
from piltover.tl import User as TLUser, Chat as TLChat, Channel as TLChannel

IntFlagT = TypeVar("IntFlagT", bound=IntFlag)


class IntFlagFieldInstance(tortoise.fields.BigIntField):
    def __init__(self, enum_type: type[IntFlag], **kwargs: Any) -> None:
        for item in enum_type:
            try:
                int(item.value)
            except ValueError:
                raise tortoise.ConfigurationError("IntFlagField only supports integer enums!")

        if "description" not in kwargs:
            kwargs["description"] = "\n".join([f"{e.name}: {int(e.value)}" for e in enum_type])[:2048]

        super().__init__(**kwargs)
        self.enum_type = enum_type

    def to_python_value(self, value: int | None) -> IntFlag | None:
        value = self.enum_type(value) if value is not None else None
        return value

    def to_db_value(self, value: IntFlag | int | None, instance: type[tortoise.Model] | tortoise.Model) -> int | None:
        if isinstance(value, IntFlag):
            value = int(value)
        if isinstance(value, int):
            value = int(self.enum_type(value))
        self.validate(value)
        return value


def IntFlagField(enum_type: type[IntFlagT], **kwargs: Any) -> IntFlagT:
    return IntFlagFieldInstance(enum_type, **kwargs)  # type: ignore


class ModelWithQueryUsersChats(Protocol):
    def query_users_chats(
            self, users: Q | None = None, chats: Q | None = None, channels: Q | None = None,
    ) -> tuple[Q | None, Q | None, Q | None]:
        ...


async def resolve_users_chats(
        user: models.User, users_q: Q | None = None, chats_q: Q | None = None, channels_q: Q | None = None,
        users: dict[int, TLUser] | None = None, chats: dict[int, TLChat] | None = None,
        channels: dict[int, TLChannel] | None = None,
) -> tuple[dict[int, TLUser] | None, dict[int, TLChat] | None, dict[int, TLChannel] | None]:
    q_empty = Q()

    if users_q is not None and users_q != q_empty:
        users_q &= Q(id__not_in=list(users.keys()))
        rel_user: models.User
        async for rel_user in models.User.filter(users_q):
            users[rel_user.id] = await rel_user.to_tl(user)
    if chats_q is not None and chats_q != q_empty:
        chats_q &= Q(id__not_in=list(chats.keys()))
        rel_chat: models.Chat
        async for rel_chat in models.Chat.filter(chats_q):
            chats[rel_chat.id] = await rel_chat.to_tl(user)
    if channels_q is not None and channels_q != q_empty:
        channels_q &= Q(id__not_in=list(channels.keys()))
        rel_channel: models.Channel
        async for rel_channel in models.Channel.filter(channels_q):
            channels[rel_channel.id] = await rel_channel.to_tl(user)

    return users, chats, channels


async def fetch_users_chats(
        obj: ModelWithQueryUsersChats, user: models.User, users: dict[int, TLUser] | None = None,
        chats: dict[int, TLChat] | None = None, channels: dict[int, TLChannel] | None = None,
) -> tuple[dict[int, TLUser] | None, dict[int, TLChat] | None, dict[int, TLChannel] | None]:
    logger.warning("tl_users_chats() should not be used!")
    q_empty = Q()
    users_q = q_empty if users is not None else None
    chats_q = q_empty if chats is not None else None
    channels_q = q_empty if channels is not None else None

    users_q, chats_q, channels_q = obj.query_users_chats(users_q, chats_q, channels_q)

    return await resolve_users_chats(user, users_q, chats_q, channels_q, users, chats, channels)