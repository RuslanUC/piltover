from __future__ import annotations

import hmac
from datetime import datetime, timedelta
from hashlib import sha256
from os import urandom
from time import time

from loguru import logger
from tortoise import fields, Model

from piltover.app_config import AppConfig
from piltover.db import models
from piltover.tl import Long, Int


def gen_access_hash() -> int:
    return int.from_bytes(urandom(7))


def gen_expires() -> datetime:
    return datetime.now() + timedelta(days=7)


class FileAccess(Model):
    id: int = fields.BigIntField(pk=True)
    access_hash: int = fields.BigIntField(default=gen_access_hash)
    file: models.File = fields.ForeignKeyField("models.File", on_delete=fields.CASCADE)
    user: models.User = fields.ForeignKeyField("models.User", on_delete=fields.CASCADE)

    file_id: int
    user_id: int

    class Meta:
        unique_together = (
            ("file", "user",),
        )

    def create_file_ref(self) -> bytes:
        created_at = Int.write(int(time() // 60))
        payload = Long.write(self.user_id) + Long.write(self.file_id) + created_at

        return created_at + hmac.new(AppConfig.FILE_REF_KEY, payload, sha256).digest()

    @staticmethod
    def is_file_ref_valid(file_ref: bytes, user_id: int | None = None, file_id: int | None = None) -> bool:
        if len(file_ref) != (4 + 256 // 8):
            return False

        now_minutes = time() // 60
        created_at = Int.read_bytes(file_ref[:4])
        if (created_at + AppConfig.FILE_REF_EXPIRE_MINUTES) < now_minutes:
            logger.error(1)
            return False

        if user_id is not None and file_id is not None:
            payload = Long.write(user_id) + Long.write(file_id) + file_ref[:4]

            if hmac.new(AppConfig.FILE_REF_KEY, payload, sha256).digest() != file_ref[4:]:
                logger.error(2)
                return False

        return True
