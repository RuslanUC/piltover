from io import BytesIO
from typing import Literal

from aiocache import BaseCache
from aiocache.serializers import BaseSerializer

from piltover.tl import TLObject, Int, Long, Int128, Int256, IntVector, LongVector, FloatVector, Int128Vector, \
    Int256Vector, BoolVector, BytesVector, StringVector, TLObjectVector
from piltover.tl.serialization_utils import SerializationUtils


class TLSerializer(BaseSerializer):
    _TYPES = [
        TLObject, Int, Long, Int128, Int256, float, bool, bytes, str,
        IntVector, LongVector, FloatVector, Int128Vector, Int256Vector, BoolVector, BytesVector, StringVector,
        TLObjectVector,
    ]
    _TYPES_TO_INT = {typ: idx for idx, typ in enumerate(_TYPES)}

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.encoding = None

    def dumps(self, value: TLObject | int | str | bytes | bool | float | None) -> bytes:
        ser_type = bytes([0 if isinstance(value, TLObject) else self._TYPES_TO_INT[type(value)]])
        return ser_type + SerializationUtils.write(value)

    def loads(self, value: bytes | None) -> TLObject | int | str | bytes | bool | float | None:
        if value is None or len(value) < 5 or value[0] < 0 or value[0] > len(self._TYPES):
            return None

        stream = BytesIO(value)
        typ = self._TYPES[stream.read(1)[0]]
        return SerializationUtils.read(stream, typ)


class NoCache(BaseCache):
    async def _get(self, key, encoding="utf-8", _conn=None) -> None:
        return None

    async def _gets(self, key, encoding="utf-8", _conn=None) -> None:
        return None

    async def _multi_get(self, keys, encoding="utf-8", _conn=None) -> list[None]:
        return [None for _ in keys]

    async def _set(self, key, value, ttl=None, _cas_token=None, _conn=None) -> bool:
        return True

    async def _multi_set(self, pairs, ttl=None, _conn=None) -> bool:
        return True

    async def _add(self, key, value, ttl=None, _conn=None) -> bool:
        return True

    async def _exists(self, key, _conn=None) -> bool:
        return False

    async def _increment(self, key, delta, _conn=None) -> int:
        return delta

    async def _expire(self, key, ttl, _conn=None) -> bool:
        return False

    async def _delete(self, key, _conn=None) -> int:
        return 0

    async def _clear(self, namespace=None, _conn=None) -> bool:
        return True

    async def _raw(self, command, *args, encoding="utf-8", _conn=None, **kwargs) -> None:
        return None

    async def _redlock_release(self, key, value) -> int:
        return 0


class Cache:
    obj: BaseCache = NoCache()

    @classmethod
    def init(cls, backend: Literal["memory", "redis", "memcached", "none"], **backend_kwargs) -> None:
        if cls.obj is not None:
            return

        backend_kwargs.pop("serializer", None)
        serializer = TLSerializer()

        if backend == "memory":
            from aiocache import SimpleMemoryCache
            cls.obj = SimpleMemoryCache(serializer=serializer)
        elif backend == "redis":
            from aiocache import RedisCache
            cls.obj = RedisCache(serializer=serializer, **backend_kwargs)
        elif backend == "memcached":
            backend_kwargs.pop("db", None)
            from aiocache import MemcachedCache
            cls.obj = MemcachedCache(serializer=serializer, **backend_kwargs)
        elif backend == "none":
            cls.obj = NoCache()
        else:
            raise ValueError(f"Unsupported cache backend: {backend}")
