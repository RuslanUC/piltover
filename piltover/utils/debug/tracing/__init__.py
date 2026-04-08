from abc import ABC, abstractmethod
from typing import Literal


class TraceTime:
    __slots__ = ("ms",)

    def __init__(self) -> None:
        self.ms = None


class BaseTracerContext(ABC):
    @abstractmethod
    def __enter__(self) -> TraceTime:
        ...

    @abstractmethod
    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        ...


class BaseTracer(ABC):
    @abstractmethod
    def __call__(self, trace_name: str, **kwargs) -> BaseTracerContext:
        ...


class NoOpTracerContext(BaseTracerContext):
    def __enter__(self) -> TraceTime:
        return TraceTime()

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        ...


class NoOpTracer(BaseTracer):
    ctx = NoOpTracerContext()

    def __call__(self, *args, **kwargs) -> NoOpTracerContext:
        return self.ctx


class Tracing:
    obj: BaseTracer = NoOpTracer()

    @classmethod
    def init(cls, backend: Literal["console", "zipkin", "noop"] | None, **backend_kwargs) -> None:
        if backend == "console":
            from .console_tracer import ConsoleTracer
            cls.obj = ConsoleTracer()
        elif backend == "zipkin":
            from .zipkin_tracer import ZipkinTracer
            cls.obj = ZipkinTracer(**backend_kwargs)
        elif backend in ("noop", None):
            cls.obj = NoOpTracer()
        else:
            raise ValueError(f"Unsupported tracing backend: {backend!r}")

    def __new__(cls, trace_name: str, **kwargs) -> BaseTracerContext:
        return cls.obj.__call__(trace_name, **kwargs)
