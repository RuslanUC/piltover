from time import perf_counter
from contextlib import contextmanager
from typing import Generator

from piltover.utils.debug.tracing import Tracing, TraceTime


@contextmanager
def measure_time(name: str, **kwargs) -> Generator[TraceTime, None, None]:
    with Tracing(name, **kwargs) as time:
        yield time


@contextmanager
def measure_time_to_dict(name: str, out: dict[str, float]) -> Generator[None, None, None]:
    start_time = perf_counter()
    try:
        yield
    finally:
        out[name] += perf_counter() - start_time
