from __future__ import annotations

from enum import IntFlag
from typing import Any, TypeVar, Protocol, Iterable

import tortoise
from tortoise.exceptions import ValidationError
from tortoise.expressions import Q
from tortoise.validators import Validator

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


Q_EMPTY = Q()


async def fetch_users_chats(
        users_q: Q | None = None, chats_q: Q | None = None, channels_q: Q | None = None,
        users: dict[int, TLUser] | None = None, chats: dict[int, TLChat] | None = None,
        channels: dict[int, TLChannel] | None = None,
) -> tuple[dict[int, models.User] | None, dict[int, models.Chat] | None, dict[int, models.Channel] | None]:
    users_out = None
    chats_out = None
    channels_out = None

    user: models.User
    chat: models.Chat
    channel: models.Channel

    if users_q is not None and users_q != Q_EMPTY:
        if users:
            users_q &= Q(id__not_in=list(users.keys()))
        users_out = {user.id: user async for user in models.User.filter(users_q)}
    if chats_q is not None and chats_q != Q_EMPTY:
        if chats:
            chats_q &= Q(id__not_in=list(chats.keys()))
        chats_out = {chat.id: chat async for chat in models.Chat.filter(chats_q)}
    if channels_q is not None and channels_q != Q_EMPTY:
        if channels:
            channels_q &= Q(id__not_in=list(channels.keys()))
        channels_out = {channel.id: channel async for channel in models.Channel.filter(channels_q)}

    return users_out, chats_out, channels_out


async def resolve_users_chats(
        user: models.User, users_q: Q | None = None, chats_q: Q | None = None, channels_q: Q | None = None,
        users: dict[int, TLUser] | None = None, chats: dict[int, TLChat] | None = None,
        channels: dict[int, TLChannel] | None = None,
) -> tuple[dict[int, TLUser] | None, dict[int, TLChat] | None, dict[int, TLChannel] | None]:
    users_f, chats_f, channels_f = await fetch_users_chats(users_q, chats_q, channels_q, users, chats, channels)

    if users_f is not None:
        for rel_user in users_f.values():
            users[rel_user.id] = await rel_user.to_tl(user)
    if chats_f is not None:
        for rel_chat in chats_f.values():
            chats[rel_chat.id] = await rel_chat.to_tl(user)
    if channels_f is not None:
        for rel_channel in channels_f.values():
            channels[rel_channel.id] = await rel_channel.to_tl(user)

    return users, chats, channels


def and_Q_to_kwargs(q: Q, _result: dict[str, Any] | None = None) -> dict[str, Any]:
    _result = _result if _result is not None else {}

    if q.join_type == Q.OR:
        return _result

    _result.update(q.filters)

    for child_q in q.children:
        and_Q_to_kwargs(child_q, _result)

    return _result
