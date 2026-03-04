from contextvars import ContextVar, Token
from time import perf_counter

import aiozipkin

from piltover.utils.debug.tracing import BaseTracer, TraceTime, BaseTracerContext


_parent_span: ContextVar[aiozipkin.SpanAbc | None] = ContextVar("_parent_span", default=None)


class ZipkinTracerContext(BaseTracerContext):
    __slots__ = ("trace_name", "zipkin", "start", "time", "span", "ctx_token",)

    def __init__(self, trace_name: str, zipkin: aiozipkin.Tracer) -> None:
        self.trace_name = trace_name
        self.zipkin = zipkin
        self.start = None
        self.time = None
        self.span: aiozipkin.SpanAbc | None = None
        self.ctx_token: Token | None = None

    def __enter__(self) -> TraceTime:
        if _parent_span.get() is None:
            self.span = self.zipkin.new_trace(sampled=True)
        else:
            self.span = _parent_span.get().new_child()

        self.ctx_token = _parent_span.set(self.span)

        self.span.name(self.trace_name)
        self.span.kind(aiozipkin.SERVER)
        self.span.start()

        self.start = perf_counter()
        self.time = TraceTime()
        return self.time

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.span.finish(exception=exc_val)
        end = perf_counter()
        _parent_span.reset(self.ctx_token)
        self.time.ms = (end - self.start) * 1000


class ZipkinTracer(BaseTracer):
    def __init__(self, zipkin_address: str) -> None:
        self._tracer = aiozipkin.Tracer(
            aiozipkin.transport.Transport(zipkin_address, send_interval=5),
            aiozipkin.Sampler(sample_rate=1.0),
            aiozipkin.create_endpoint("piltover", ipv4="127.0.0.1", port=8080),
        )

    def __call__(self, trace_name: str, **kwargs) -> ZipkinTracerContext:
        return ZipkinTracerContext(trace_name, self._tracer)
