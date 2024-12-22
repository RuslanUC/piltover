from datetime import datetime
from os import getpid
from random import randint
from time import time

from pytz import UTC


class Snowflake:
    EPOCH = 1704067200_000  # 01.01.2024, 00:00:00
    MAX_TIMESTAMP = 1 << 42
    _INCREMENT = 0
    _WORKER = randint(0, 32)
    _PROCESS = getpid()

    @classmethod
    def make_id(cls, increment: bool = True) -> int:
        timestamp = int(time() * 1000) - cls.EPOCH

        snowflake = (timestamp % cls.MAX_TIMESTAMP) << 22
        snowflake += (cls._WORKER % 32) << 17
        snowflake += (cls._PROCESS % 32) << 12
        snowflake += cls._INCREMENT % 4096

        if increment:
            cls._INCREMENT += 1

        return snowflake

    @classmethod
    def from_timestamp(cls, timestamp: int | float) -> int:
        timestamp = int(timestamp * 1000) - cls.EPOCH

        snowflake = (timestamp % cls.MAX_TIMESTAMP) << 22
        snowflake += (cls._WORKER % 32) << 17
        snowflake += (cls._PROCESS % 32) << 12
        snowflake += cls._INCREMENT % 4096

        return snowflake

    @classmethod
    def to_datetime(cls, snowflake: int) -> datetime:
        timestamp = ((snowflake >> 22) + cls.EPOCH) / 1000
        return datetime.fromtimestamp(timestamp, tz=UTC)
