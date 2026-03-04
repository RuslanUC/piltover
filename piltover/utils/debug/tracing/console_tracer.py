from contextvars import ContextVar, Token
from os import environ
from time import perf_counter

from loguru import logger

from piltover.utils.debug.tracing import BaseTracer, TraceTime, BaseTracerContext


_measure_time_loglevel = environ.get("DEBUG_MEASURETIME_LOG", "TRACE")
_measure_time_end_loglevel = environ.get("DEBUG_MEASURETIME_END_LOG", _measure_time_loglevel)
_measure_time_level: ContextVar[int] = ContextVar("_measure_time_level", default=0)


class ConsoleTracerContext(BaseTracerContext):
    __slots__ = ("trace_name", "loglevel", "end_loglevel", "start", "time",)

    def __init__(self, trace_name: str, loglevel: str, end_loglevel: str) -> None:
        self.trace_name = trace_name
        self.loglevel = loglevel
        self.end_loglevel = end_loglevel
        self.start = None
        self.time = None
        self.ctx_token: Token | None = None

    def __enter__(self) -> TraceTime:
        level = _measure_time_level.get()
        hyphens = "-" * level * 2

        logger.opt(depth=2).log(self.loglevel, f"---{hyphens}> running {self.trace_name}...")
        self.ctx_token = _measure_time_level.set(level + 1)

        self.start = perf_counter()
        self.time = TraceTime()
        return self.time

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        end = perf_counter()
        time_spent_ms = (end - self.start) * 1000
        _measure_time_level.reset(self.ctx_token)
        level = _measure_time_level.get()
        hyphens = "-" * level * 2
        logger.opt(depth=2).log(self.end_loglevel, f"<---{hyphens} {self.trace_name} took {time_spent_ms:.2f}ms")
        self.time.ms = time_spent_ms


class ConsoleTracer(BaseTracer):
    def __call__(
            self,
            trace_name: str,
            *,
            loglevel: str = _measure_time_loglevel,
            end_loglevel: str = _measure_time_end_loglevel,
            **kwargs,
    ) -> ConsoleTracerContext:
        return ConsoleTracerContext(trace_name, loglevel, end_loglevel)
