from io import BytesIO
from typing import Literal

from aiocache import BaseCache
from aiocache.serializers import BaseSerializer

from piltover.tl import TLObject, SerializationUtils, Int, Long, Int128, Int256


class TLSerializer(BaseSerializer):
    _TYPES = [TLObject, Int, Long, Int128, Int256, float, bool, bytes, str, list]
    _TYPES_TO_INT = {typ: idx for idx, typ in enumerate(_TYPES)}

    def dumps(self, value: TLObject | int | str | bytes | bool | list | float | None) -> bytes:
        ser_type = bytes([0 if isinstance(value, TLObject) else self._TYPES_TO_INT[type(value)]])
        vec_type = b""
        if isinstance(value, list):
            vec_type = bytes([0 if isinstance(value, TLObject) or not value else self._TYPES_TO_INT[type(value[0])]])

        return ser_type + vec_type + SerializationUtils.write(value)

    def loads(self, value: bytes | None) -> TLObject | int | str | bytes | bool | list | float | None:
        if value is None or len(value) < 5 or value[0] < 0 or value[0] > len(self._TYPES):
            return None

        stream = BytesIO(value)

        typ = self._TYPES[stream.read(1)[0]]
        subtyp = None
        if typ is list:
            if value[1] < 0 or value[1] > len(self._TYPES):
                return None
            subtyp = self._TYPES[stream.read(1)[0]]

        return SerializationUtils.read(stream, typ, subtyp)


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
