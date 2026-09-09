from __future__ import annotations

from contextvars import ContextVar
from typing import Any
from collections.abc import Iterable, Callable

from loguru import logger
from tortoise import BaseDBAsyncClient
from tortoise.backends.base.client import PoolConnectionWrapper
from tortoise.backends.base.executor import BaseExecutor
from tortoise.queryset import BulkCreateQuery, BulkUpdateQuery, RawSQLQuery, ValuesQuery, ValuesListQuery, \
    CountQuery, ExistsQuery, DeleteQuery, UpdateQuery, QuerySet, AwaitableQuery

try:
    from tortoise.queryset_compiled import CompiledQuerySet
except ImportError:
    CompiledQuerySet = None

from tortoise.backends.sqlite import SqliteClient

try:
    from tortoise.backends.mysql import MySQLClient
except ImportError:
    MySQLClient = None

from piltover.session import Session
from piltover.utils.debug import measure_time
from piltover.worker import RequestHandler

query_clss: list[type[AwaitableQuery]] = [
    BulkCreateQuery, BulkUpdateQuery, RawSQLQuery, ValuesQuery, ValuesListQuery, CountQuery, ExistsQuery,
    DeleteQuery, UpdateQuery, QuerySet,
]
if CompiledQuerySet is not None:
    query_clss.append(CompiledQuerySet)
client_clss: list[type[BaseDBAsyncClient]] = [
    SqliteClient,
]
if MySQLClient is not None:
    client_clss.append(MySQLClient)
execute_methods = ("execute", "_execute_many", "_execute",)
make_query_methods = ("_get_or_create_cached_sql", "_make_queries", "_make_query",)
call_methods = ("__call__",)
resolve_ctx_methods = ("_resolve_context_values",)
executor_select_methods = ("execute_select",)
client_methods = ("execute_insert", "execute_query", "execute_script", "execute_many")
aenter_methods = ("__aenter__",)
aexit_methods = ("__aexit__",)
real_suffix = "_real"
handler_stats_ctx: ContextVar[QueryStats] = ContextVar("handler_stats_ctx")
_using_executor_ctx: ContextVar[bool] = ContextVar("_using_executor_ctx", default=False)


class QueryStats:
    def __init__(self) -> None:
        self.make_query_count = 0
        self.make_query_time = 0
        self.execute_count = 0
        self.execute_time = 0
        self.executor_count = 0
        self.executor_time = 0
        self.client_count = 0
        self.client_time = 0

    def reset(self) -> None:
        self.make_query_count = 0
        self.make_query_time = 0
        self.execute_count = 0
        self.execute_time = 0
        self.executor_count = 0
        self.executor_time = 0
        self.client_count = 0
        self.client_time = 0

    def add(self, stats: QueryStats) -> None:
        self.make_query_count += stats.make_query_count
        self.make_query_time += stats.make_query_time
        self.execute_count += stats.execute_count
        self.execute_time += stats.execute_time
        self.executor_count += stats.executor_count
        self.executor_time += stats.executor_time
        self.client_count += stats.client_count
        self.client_time += stats.client_time


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
        real_method: Callable | None = getattr(obj, f"{name}{suffix}", None)
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
                f"that took {query_stats.execute_time:.2f}ms ({query_stats.make_query_time:.2f}ms)"
            )

    _patch_cls_replace_method(RequestHandler, call_methods, real_suffix, _RequestHandler___call__)

    async def _Session__resolve_context_values(*args, **kwargs):
        _, _resolve_real = _get_patched_cls_original_method(Session, resolve_ctx_methods, real_suffix)
        query_stats = QueryStats()
        token = handler_stats_ctx.set(query_stats)
        try:
            return await _resolve_real(*args, **kwargs)
        finally:
            handler_stats_ctx.reset(token)
            query_stats_all.add(query_stats)
            logger.info(
                f"_resolve_context_values made {query_stats.execute_count} ({query_stats.make_query_count}) queries "
                f"that took {query_stats.execute_time:.2f}ms ({query_stats.make_query_time:.2f}ms)"
            )

    _patch_cls_replace_method(Session, resolve_ctx_methods, real_suffix, _Session__resolve_context_values)

    async def _BaseExecutor_execute_select(self: BaseExecutor, *args, **kwargs):
        name, execute_real = _get_patched_cls_original_method(self, executor_select_methods, real_suffix)
        token = _using_executor_ctx.set(True)
        try:
            with measure_time(f"{self.__class__.__name__}.{name}()", add_depth=3) as _time_spent:
                result = await execute_real(*args, **kwargs)
        finally:
            _using_executor_ctx.reset(token)

        query_stats = handler_stats_ctx.get(None)
        if query_stats is not None:
            query_stats.executor_count += 1
            query_stats.executor_time += _time_spent.ms

        return result

    _patch_cls_replace_method(BaseExecutor, executor_select_methods, real_suffix, _BaseExecutor_execute_select)

    for cls in query_clss:
        async def _execute(self: AwaitableQuery, *args, **kwargs) -> Any:
            name, execute_real = _get_patched_cls_original_method(self, execute_methods, real_suffix)
            with measure_time(f"{self.__class__.__name__}.{name}()", add_depth=1) as _time_spent:
                result = await execute_real(*args, **kwargs)

            query_stats = handler_stats_ctx.get(None)
            if query_stats is not None:
                query_stats.execute_count += 1
                query_stats.execute_time += _time_spent.ms

            return result

        def _make_query(self: AwaitableQuery, *args, **kwargs) -> Any:
            name, make_query_real = _get_patched_cls_original_method(self, make_query_methods, real_suffix)
            with measure_time(f"{self.__class__.__name__}.{name}()", add_depth=2) as _time_spent:
                result = make_query_real(*args, **kwargs)

            query_stats = handler_stats_ctx.get(None)
            if query_stats is not None:
                query_stats.make_query_count += 1
                query_stats.make_query_time += _time_spent.ms

            return result

        _patch_cls_replace_method(cls, execute_methods, real_suffix, _execute)
        _patch_cls_replace_method(cls, make_query_methods, real_suffix, _make_query)

    for cls in client_clss:
        for method in client_methods:
            async def _execute(self: BaseDBAsyncClient, *args, __original_method=method, **kwargs) -> Any:
                depth = 3 + _using_executor_ctx.get() * 2
                name, execute_real = _get_patched_cls_original_method(self, (__original_method,), real_suffix)
                with measure_time(f"{self.__class__.__name__}.{name}()", add_depth=depth) as _time_spent:
                    result = await execute_real(*args, **kwargs)

                query_stats = handler_stats_ctx.get(None)
                if query_stats is not None:
                    query_stats.client_count += 1
                    query_stats.client_time += _time_spent.ms

                return result

            _execute.__name__ = f"_{cls.__name__}_{method}"
            _patch_cls_replace_method(cls, (method,), real_suffix, _execute)

    async def _PoolConnectionWrapper___aenter(self: PoolConnectionWrapper, *args, **kwargs):
        depth = 6 + _using_executor_ctx.get() * 2
        name, execute_real = _get_patched_cls_original_method(self, aenter_methods, real_suffix)
        with measure_time(f"{self.__class__.__name__}.{name}()", add_depth=depth) as _time_spent:
            return await execute_real(*args, **kwargs)

    _patch_cls_replace_method(PoolConnectionWrapper, aenter_methods, real_suffix, _PoolConnectionWrapper___aenter)

    async def _PoolConnectionWrapper___aexit(self: PoolConnectionWrapper, *args, **kwargs):
        depth = 6 + _using_executor_ctx.get() * 2
        name, execute_real = _get_patched_cls_original_method(self, aexit_methods, real_suffix)
        with measure_time(f"{self.__class__.__name__}.{name}()", add_depth=depth) as _time_spent:
            return await execute_real(*args, **kwargs)

    _patch_cls_replace_method(PoolConnectionWrapper, aexit_methods, real_suffix, _PoolConnectionWrapper___aexit)

    return query_stats_all


def unpatch_queryset_for_measurement() -> None:
    for cls in query_clss:
        _unpatch_cls_replaced_method(cls, execute_methods, real_suffix)
        _unpatch_cls_replaced_method(cls, make_query_methods, real_suffix)

    for cls in client_clss:
        for method in client_methods:
            _unpatch_cls_replaced_method(cls, (method,), real_suffix)

    _unpatch_cls_replaced_method(BaseExecutor, executor_select_methods, real_suffix)
    _unpatch_cls_replaced_method(RequestHandler, call_methods, real_suffix)
    _unpatch_cls_replaced_method(Session, resolve_ctx_methods, real_suffix)
    _unpatch_cls_replaced_method(PoolConnectionWrapper, aenter_methods, real_suffix)
    _unpatch_cls_replaced_method(PoolConnectionWrapper, aexit_methods, real_suffix)
