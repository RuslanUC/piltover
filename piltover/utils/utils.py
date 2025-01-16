import asyncio
from typing import TypeVar, Coroutine, Callable, Awaitable

T = TypeVar("T")
TAdd = TypeVar("TAdd")


def background(coro: Coroutine[None, None, T]) -> asyncio.Task[T]:
    loop = asyncio.get_event_loop()
    task = loop.create_task(coro)
    return task


class classinstancemethod:
    def __init__(self, method: Callable, instance: object = None, owner=None):
        self.method = method
        self.instance = instance
        self.owner = owner

    def __get__(self, instance: object, owner=None):
        return type(self)(self.method, instance, owner)

    def __call__(self, *args, **kwargs):
        instance = self.instance
        if instance is None:
            if not args:
                raise TypeError('missing required parameter "self"')
            instance, args = args[0], args[1:]

        cls = self.owner
        return self.method(cls, instance, *args, **kwargs)


def xor(a: bytes, b: bytes) -> bytes:
    return bytes(i ^ j for i, j in zip(a, b))


def sec_check(cond: ..., exc: type[Exception] = Exception, msg: str | None = None) -> None:
    if not cond:
        raise exc(msg) if msg else exc


async def run_coro_with_additional_return(coro: Awaitable[T], additional_obj: TAdd) -> tuple[T, TAdd]:
    return await coro, additional_obj
