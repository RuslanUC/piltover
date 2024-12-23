import asyncio
from typing import TypeVar, Coroutine, Callable


T = TypeVar("T")


def background(coro: Coroutine[None, None, T]) -> asyncio.Task[T]:
    loop = asyncio.get_event_loop()
    task = loop.create_task(coro)
    return task


def check_flag(flags: int, *check: int) -> bool:
    for flag in check:
        if (flags & flag) != flag:
            return False
    return True


class SingletonMeta(type):
    _instances = {}

    def __call__(cls, *args, **kwargs):
        if cls not in cls._instances:
            instance = super().__call__(*args, **kwargs)
            cls._instances[cls] = instance
        return cls._instances[cls]


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
