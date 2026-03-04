from contextlib import contextmanager
from typing import Generator

from piltover.utils.debug.tracing import Tracing, TraceTime


@contextmanager
def measure_time(name: str, **kwargs) -> Generator[TraceTime, None, None]:
    with Tracing(name, **kwargs) as time:
        yield time
