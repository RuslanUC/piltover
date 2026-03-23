from __future__ import annotations

from contextvars import ContextVar
from typing import Iterable, Callable

from loguru import logger
from tortoise.queryset import BulkCreateQuery, BulkUpdateQuery, RawSQLQuery, ValuesQuery, ValuesListQuery, \
    CountQuery, ExistsQuery, DeleteQuery, UpdateQuery, QuerySet, AwaitableQuery
from tortoise.queryset_compiled import CompiledQuerySet

from piltover.gateway import Client
from piltover.utils.debug import measure_time
from piltover.worker import RequestHandler

query_clss = [
    BulkCreateQuery, BulkUpdateQuery, RawSQLQuery, ValuesQuery, ValuesListQuery, CountQuery, ExistsQuery,
    DeleteQuery, UpdateQuery, QuerySet, CompiledQuerySet
]
execute_methods = ("execute", "_execute_many", "_execute",)
make_query_methods = ("_get_or_create_cached_sql", "_make_queries", "_make_query",)
call_methods = ("__call__",)
resolve_ctx_methods = ("_resolve_context_values",)
real_suffix = "_real"
handler_stats_ctx: ContextVar[QueryStats] = ContextVar("handler_stats_ctx")


class QueryStats:
    def __init__(self) -> None:
        self.make_query_count = 0
        self.make_query_time = 0
        self.execute_count = 0
        self.execute_time = 0

    def reset(self) -> None:
        self.make_query_count = 0
        self.make_query_time = 0
        self.execute_count = 0
        self.execute_time = 0

    def add(self, stats: QueryStats) -> None:
        self.make_query_count += stats.make_query_count
        self.make_query_time += stats.make_query_time
        self.execute_count += stats.execute_count
        self.execute_time += stats.execute_time


def _patch_cls_replace_method(cls: type, names: Iterable[str], suffix: str, replace_with: Callable) -> None:
    for name in names:
        if not hasattr(cls, name):
            continue

        setattr(cls, f"{name}{suffix}", getattr(cls, name))
        setattr(cls, name, replace_with)
        return


def _get_patched_cls_original_method(obj: object, names: Iterable[str], suffix: str) -> tuple[str, Callable]:
    from piltover.exceptions import Unreachable

    for name in names:
        real_method = getattr(obj, f"{name}{suffix}", None)
        if real_method is not None:
            return name, real_method

    raise Unreachable


def _unpatch_cls_replaced_method(cls: type, names: Iterable[str], suffix: str) -> None:
    for name in names:
        real_name = f"{name}{suffix}"
        if not hasattr(cls, real_name):
            continue

        setattr(cls, name, getattr(cls, real_name))
        delattr(cls, real_name)
        return


def patch_queryset_for_measurement() -> QueryStats:
    query_stats_all = QueryStats()

    async def _RequestHandler___call__(self: RequestHandler, *args, **kwargs):
        _, _call_real = _get_patched_cls_original_method(self, call_methods, real_suffix)
        query_stats = QueryStats()
        token = handler_stats_ctx.set(query_stats)
        try:
            return await _call_real(*args, **kwargs)
        finally:
            handler_stats_ctx.reset(token)
            query_stats_all.add(query_stats)
            logger.info(
                f"{self.func.__name__} made {query_stats.execute_count} ({query_stats.make_query_count}) queries "
                f"that took {query_stats.execute_count:.2f}ms ({query_stats.make_query_time:.2f}ms)"
            )

    _patch_cls_replace_method(RequestHandler, call_methods, real_suffix, _RequestHandler___call__)

    async def _Client__resolve_context_values(*args, **kwargs):
        _, _resolve_real = _get_patched_cls_original_method(Client, resolve_ctx_methods, real_suffix)
        query_stats = QueryStats()
        token = handler_stats_ctx.set(query_stats)
        try:
            return await _resolve_real(*args, **kwargs)
        finally:
            handler_stats_ctx.reset(token)
            query_stats_all.add(query_stats)
            logger.info(
                f"_resolve_context_values made {query_stats.execute_count} ({query_stats.make_query_count}) queries "
                f"that took {query_stats.execute_count:.2f}ms ({query_stats.make_query_time:.2f}ms)"
            )

    _patch_cls_replace_method(Client, resolve_ctx_methods, real_suffix, staticmethod(_Client__resolve_context_values))

    for cls in query_clss:
        async def _execute(self: AwaitableQuery, *args, **kwargs) -> ...:
            name, execute_real = _get_patched_cls_original_method(self, execute_methods, real_suffix)
            with measure_time(f"{self.__class__.__name__}.{name}()") as _time_spent:
                result = await execute_real(*args, **kwargs)

            query_stats = handler_stats_ctx.get(None)
            if query_stats is not None:
                query_stats.execute_count += 1
                query_stats.execute_time += _time_spent.ms

            return result

        def _make_query(self: AwaitableQuery, *args, **kwargs) -> ...:
            name, make_query_real = _get_patched_cls_original_method(self, make_query_methods, real_suffix)
            with measure_time(f"{self.__class__.__name__}.{name}()") as _time_spent:
                result = make_query_real(*args, **kwargs)

            query_stats = handler_stats_ctx.get(None)
            if query_stats is not None:
                query_stats.make_query_count += 1
                query_stats.make_query_time += _time_spent.ms

            return result

        _patch_cls_replace_method(cls, execute_methods, real_suffix, _execute)
        _patch_cls_replace_method(cls, make_query_methods, real_suffix, _make_query)

    return query_stats_all


def unpatch_queryset_for_measurement() -> None:
    for cls in query_clss:
        _unpatch_cls_replaced_method(cls, execute_methods, real_suffix)
        _unpatch_cls_replaced_method(cls, make_query_methods, real_suffix)

    _unpatch_cls_replaced_method(RequestHandler, call_methods, real_suffix)
