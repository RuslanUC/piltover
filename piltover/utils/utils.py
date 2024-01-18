import asyncio
from hashlib import sha256
from io import BytesIO
from typing import TypeVar, Coroutine, Callable


def read_int(data: bytes) -> int:
    return int.from_bytes(data, byteorder="little")


def write_bytes(value: bytes, to: BytesIO):
    length = len(value)

    if length <= 253:
        to.write(bytes([length]) + value + bytes(-(length + 1) % 4))
    else:
        to.write(bytes([254]) + length.to_bytes(3, "little") + value + bytes(-length % 4))


def kdf(auth_key: bytes, msg_key: bytes, outgoing: bool) -> tuple:
    # taken from pyrogram, mtproto.py
    # https://core.telegram.org/mtproto/description#defining-aes-key-and-initialization-vector
    x = 0 if outgoing else 8

    sha256_a = sha256(msg_key + auth_key[x:x + 36]).digest()
    sha256_b = sha256(auth_key[x + 40:x + 76] + msg_key).digest()  # 76 = 40 + 36

    aes_key = sha256_a[:8] + sha256_b[8:24] + sha256_a[24:32]
    aes_iv = sha256_b[:8] + sha256_a[8:24] + sha256_b[24:32]

    return aes_key, aes_iv


_tasks = set()
T = TypeVar("T")


def background(coro: Coroutine[None, None, T]) -> asyncio.Task[T]:
    loop = asyncio.get_event_loop()
    task = loop.create_task(coro)
    _tasks.add(task)
    task.add_done_callback(_tasks.remove)
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
