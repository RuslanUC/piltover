from io import BytesIO
from typing import Literal

from aiocache import BaseCache
from aiocache.serializers import BaseSerializer

from piltover.tl import TLObject, Int, Long, Int128, Int256
from piltover.tl.serialization_utils import SerializationUtils


class TLSerializer(BaseSerializer):
    _TYPES = [TLObject, Int, Long, Int128, Int256, float, bool, bytes, str]
    _TYPES_TO_INT = {typ: idx for idx, typ in enumerate(_TYPES)}

    def dumps(self, value: TLObject | int | str | bytes | bool | float | None) -> bytes:
        ser_type = bytes([0 if isinstance(value, TLObject) else self._TYPES_TO_INT[type(value)]])
        return ser_type + SerializationUtils.write(value)

    def loads(self, value: bytes | None) -> TLObject | int | str | bytes | bool | float | None:
        if value is None or len(value) < 5 or value[0] < 0 or value[0] > len(self._TYPES):
            return None

        stream = BytesIO(value)
        typ = self._TYPES[stream.read(1)[0]]
        return SerializationUtils.read(stream, typ)


class Cache:
    obj: BaseCache | None = None

    @classmethod
    def init(cls, backend: Literal["memory", "redis", "memcached"], **backend_kwargs) -> None:
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
            from aiocache import MemcachedCache
            cls.obj = MemcachedCache(serializer=serializer, **backend_kwargs)
        else:
            raise ValueError(f"Unsupported cache backend: {backend}")
