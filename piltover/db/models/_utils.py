from __future__ import annotations

from enum import IntFlag
from typing import Any, TypeVar, cast, Self, Generator

import tortoise
from loguru import logger
from pypika_tortoise import Query, Parameterizer
from tortoise import Model
from tortoise.exceptions import DoesNotExist, MultipleObjectsReturned
from tortoise.expressions import Q, ResolveContext
from tortoise.query_utils import QueryModifier
from tortoise.queryset import QuerySet, MODEL

from piltover.db import models
from piltover.tl import User as TLUser, Chat as TLChat, Channel as TLChannel

IntFlagT = TypeVar("IntFlagT", bound=IntFlag)


class IntFlagFieldInstance(tortoise.fields.BigIntField):
    def __init__(self, enum_type: type[IntFlag], **kwargs: Any) -> None:
        for item in enum_type:
            try:
                int(cast(int | str, item.value))
            except ValueError:
                raise tortoise.ConfigurationError("IntFlagField only supports integer enums!")

        if "description" not in kwargs:
            kwargs["description"] = "\n".join([f"{e.name}: {e.value}" for e in enum_type])[:2048]

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
        users_out = {user.id: user for user in await models.User.filter(users_q)}
    if chats_q is not None and chats_q != Q_EMPTY:
        if chats:
            chats_q &= Q(id__not_in=list(chats.keys()))
        chats_out = {chat.id: chat for chat in await models.Chat.filter(chats_q)}
    if channels_q is not None and channels_q != Q_EMPTY:
        if channels:
            channels_q &= Q(id__not_in=list(channels.keys()))
        channels_out = {channel.id: channel for channel in await models.Channel.filter(channels_q)}

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


class CacheHitQuerySet(QuerySet[MODEL]):
    def __init__(self, model: type[MODEL], sql: str) -> None:
        super().__init__(model)
        self._cached_sql = sql

    def __await__(self) -> Generator[Any, None, list[MODEL]]:
        if self._db is None:
            self._db = self._choose_db(self._select_for_update)
        self._make_query()

        modifier = QueryModifier()
        for node in self._q_objects:
            modifier &= node.resolve(
                ResolveContext(
                    model=self.model,
                    table=self.model._meta.basetable,
                    annotations=self._annotations,
                    custom_filters=self._custom_filters,
                )
            )

        param = Parameterizer()
        ctx = Query.SQL_CONTEXT.copy(parameterizer=param)

        modifier.where_criterion.get_sql(ctx)
        modifier.having_criterion.get_sql(ctx)

        return self._execute(param.values).__await__()

    def filter(self, *args: Q, **kwargs: Any) -> QuerySet[MODEL]:
        new_query = cast(CacheHitQuerySet[MODEL], self._filter_or_exclude(negate=False, *args, **kwargs))
        new_query._cached_sql = self._cached_sql
        return new_query

    async def _execute(self, params: list[...]) -> list[MODEL]:
        logger.trace(f"executing cached query: {self._cached_sql} with params {params}")

        instance_list = await self._db.executor_class(
            model=self.model,
            db=self._db,
            prefetch_map=self._prefetch_map,
            prefetch_queries=self._prefetch_queries,
            select_related_idx=self._select_related_idx,  # type: ignore
        ).execute_select(
            self._cached_sql, params,
            custom_fields=list(self._annotations.keys()),
        )
        if self._single:
            if len(instance_list) == 1:
                return instance_list[0]
            if not instance_list:
                if self._raise_does_not_exist:
                    raise DoesNotExist(self.model)
                return None  # type: ignore
            raise MultipleObjectsReturned(self.model)
        return instance_list


class CachedQuerySet(QuerySet[MODEL]):
    def __init__(self, model: type[MODEL], name: str | None = None) -> None:
        super().__init__(model)
        self._cache_key = name

    def filter(self, *args: Q, **kwargs: Any) -> QuerySet[MODEL]:
        new_query = cast(CachedQuerySet[MODEL], self._filter_or_exclude(negate=False, *args, **kwargs))
        new_query._cache_key = self._cache_key

        return new_query

    def __await__(self) -> Generator[Any, None, list[MODEL]]:
        if (_query_cache := getattr(self.model.Meta, "_query_cache", None)) is None:
            _query_cache = {}
            setattr(self.model.Meta, "_query_cache", _query_cache)

        sql_to_cache = self.sql(False)
        _query_cache[self._cache_key] = sql_to_cache

        return super().__await__()


class ModelCachedQuery(Model):
    @classmethod
    def cache_query(cls, name: str) -> QuerySet[Self]:
        if (_query_cache := getattr(cls.Meta, "_query_cache", None)) is not None \
                and name in _query_cache:
            return CacheHitQuerySet(cls, _query_cache[name])
        return CachedQuerySet(cls, name)
