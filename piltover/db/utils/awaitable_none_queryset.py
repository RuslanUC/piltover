from __future__ import annotations

from typing import Any, Generator, Literal, AsyncIterator

from pypika_tortoise.terms import Term
from tortoise import BaseDBAsyncClient
from tortoise.exceptions import DoesNotExist
from tortoise.expressions import Q, Expression
from tortoise.query_utils import Prefetch
from tortoise.queryset import QuerySet, MODEL, ValuesListQuery, QuerySetSingle, ValuesQuery, DeleteQuery, \
    UpdateQuery, CountQuery, ExistsQuery


class EmptyQuerySet(QuerySet[MODEL]):
    __slots__ = ()

    def __init__(self, model: type[MODEL]) -> None:
        super().__init__(model)

    def _clone(self) -> QuerySet[MODEL]:
        queryset = self.__class__.__new__(self.__class__)
        queryset.model = self.model
        return queryset

    def filter(self, *args: Q, **kwargs: Any) -> QuerySet[MODEL]:
        return self

    def exclude(self, *args: Q, **kwargs: Any) -> QuerySet[MODEL]:
        return self

    def order_by(self, *orderings: str) -> QuerySet[MODEL]:
        return self

    def _as_single(self) -> QuerySetSingle[None]:
        queryset = self._clone()
        queryset._single = True
        return queryset

    def latest(self, *orderings: str) -> QuerySetSingle[None]:
        return self._as_single()

    def earliest(self, *orderings: str) -> QuerySetSingle[None]:
        return self._as_single()

    def limit(self, limit: int) -> QuerySet[MODEL]:
        return self

    def offset(self, offset: int) -> QuerySet[MODEL]:
        return self

    def distinct(self) -> QuerySet[MODEL]:
        return self

    def select_for_update(
        self,
        nowait: bool = False,
        skip_locked: bool = False,
        of: tuple[str, ...] = (),
        no_key: bool = False,
    ) -> QuerySet[MODEL]:
        return self

    def annotate(self, **kwargs: Expression | Term) -> QuerySet[MODEL]:
        return self

    def group_by(self, *fields: str) -> QuerySet[MODEL]:
        return self

    def values_list(self, *fields_: str, flat: bool = False) -> ValuesListQuery[Literal[False]]:
        raise NotImplementedError

    def values(self, *args: str, **kwargs: str) -> ValuesQuery[Literal[False]]:
        raise NotImplementedError

    def delete(self) -> DeleteQuery:
        raise NotImplementedError

    def update(self, **kwargs: Any) -> UpdateQuery:
        raise NotImplementedError

    def count(self) -> CountQuery:
        raise NotImplementedError

    def exists(self) -> ExistsQuery:
        raise NotImplementedError

    def all(self) -> QuerySet[MODEL]:
        return self

    def first(self) -> QuerySetSingle[None]:
        return self._as_single()

    def last(self) -> QuerySetSingle[None]:
        return self._as_single()

    def get(self, *args: Q, **kwargs: Any) -> QuerySetSingle[MODEL]:
        queryset = self._as_single()
        queryset._raise_does_not_exist = True
        return queryset

    def get_or_none(self, *args: Q, **kwargs: Any) -> QuerySetSingle[None]:
        return self._as_single()

    def only(self, *fields_for_select: str) -> QuerySet[MODEL]:
        return self

    def select_related(self, *fields: str) -> QuerySet[MODEL]:
        return self

    def force_index(self, *index_names: str) -> QuerySet[MODEL]:
        return self

    def use_index(self, *index_names: str) -> QuerySet[MODEL]:
        return self

    def prefetch_related(self, *args: str | Prefetch) -> QuerySet[MODEL]:
        return self

    def using_db(self, _db: BaseDBAsyncClient | None) -> QuerySet[MODEL]:
        return self

    async def _await(self) -> list | None:
        if self._single:
            if self._raise_does_not_exist:
                raise DoesNotExist(self.model)
            return None
        return []

    def __await__(self) -> Generator[Any, None, list[MODEL]]:
        return self._await().__await__()

    async def __aiter__(self) -> AsyncIterator[MODEL]:
        for val in await self:
            yield val
