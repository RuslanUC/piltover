from __future__ import annotations

from datetime import datetime, timedelta
from os import urandom

from pytz import UTC
from tortoise import fields

from piltover.db import models
from piltover.db.models._utils import Model


def gen_access_hash() -> int:
    return int.from_bytes(urandom(7))


def gen_file_reference() -> bytes:
    return urandom(16)


def gen_expires() -> datetime:
    return datetime.now() + timedelta(days=7)


class FileAccess(Model):
    id: int = fields.BigIntField(pk=True)
    access_hash: int = fields.BigIntField(default=gen_access_hash)
    file_reference: bytes = fields.BinaryField(default=gen_file_reference)
    expires: datetime = fields.DatetimeField(default=gen_expires)
    file: models.File = fields.ForeignKeyField("models.File", on_delete=fields.CASCADE)
    user: models.User = fields.ForeignKeyField("models.User", on_delete=fields.CASCADE)

    def is_expired(self) -> bool:
        return self.expires.replace(tzinfo=UTC) < datetime.now().replace(tzinfo=UTC)

    @classmethod
    async def get_or_renew(cls, user: models.User, file: models.File) -> FileAccess:
        access, _ = await models.FileAccess.get_or_create(file=file, user=user)
        if access.is_expired():
            await access.delete()
            access = await models.FileAccess.create(file=file, user=user)

        return access
