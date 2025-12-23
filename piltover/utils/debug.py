import asyncio
from asyncio import Future
from contextlib import contextmanager, asynccontextmanager
from os import environ
from time import perf_counter
from typing import Any, Generator

from loguru import logger

_measure_time_loglevel = environ.get("DEBUG_MEASURETIME_LOG", "TRACE")
_measure_time_end_loglevel = environ.get("DEBUG_MEASURETIME_END_LOG", _measure_time_loglevel)
_measure_time_level = 0


@contextmanager
def measure_time(
        name: str, loglevel: str = _measure_time_loglevel, end_loglevel: str = _measure_time_end_loglevel,
) -> ...:
    global _measure_time_level

    hyphens = "-" * _measure_time_level

    logger.log(loglevel, f"---{hyphens}> running {name}...")
    _measure_time_level += 1
    start = perf_counter()

    try:
        yield
    finally:
        end = perf_counter()
        _measure_time_level -= 1
        logger.log(end_loglevel, f"<---{hyphens} {name} took {(end - start) * 1000:.2f}ms")


@contextmanager
def measure_time_with_result(
        name: str, loglevel: str = _measure_time_loglevel, end_loglevel: str = _measure_time_end_loglevel,
        loop: asyncio.BaseEventLoop | None = None,
) -> Generator[Future[Any], Any, None]:
    global _measure_time_level

    hyphens = "-" * _measure_time_level

    logger.log(loglevel, f"---{hyphens}> running {name}...")
    _measure_time_level += 1
    start = perf_counter()

    if loop is None:
        loop = asyncio.get_running_loop()

    fut = loop.create_future()

    try:
        yield fut
    finally:
        end = perf_counter()
        time_spent_ms = (end - start) * 1000
        _measure_time_level -= 1
        logger.log(end_loglevel, f"<---{hyphens} {name} took {time_spent_ms:.2f}ms")
        fut.set_result(time_spent_ms)
