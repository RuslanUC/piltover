from contextlib import contextmanager
from os import environ
from time import perf_counter

from loguru import logger

_measure_time_loglevel = environ.get("DEBUG_MEASURETIME_LOG", "TRACE")
_measure_time_level = 0


@contextmanager
def measure_time(name: str, loglevel: str = _measure_time_loglevel) -> ...:
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
        logger.log(loglevel, f"<---{hyphens} {name} took {(end - start) * 1000:.2f}ms")