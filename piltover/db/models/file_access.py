from __future__ import annotations

from datetime import datetime, timedelta
from os import urandom

from pytz import UTC
from tortoise import fields, Model

from piltover.db import models


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
    expires: datetime | None = fields.DatetimeField(default=gen_expires, null=True)
    file: models.File = fields.ForeignKeyField("models.File", on_delete=fields.CASCADE)
    user: models.User = fields.ForeignKeyField("models.User", on_delete=fields.CASCADE)

    class Meta:
        unique_together = (
            ("file", "user",),
        )

    def is_expired(self) -> bool:
        return self.expires is not None and self.expires.replace(tzinfo=UTC) < datetime.now().replace(tzinfo=UTC)

    @classmethod
    async def get_or_renew(cls, user: models.User, file: models.File, real_renew: bool = False) -> FileAccess:
        if user.is_lazy:
            user = await models.User.get(id=user.id)

        access, created = await models.FileAccess.get_or_create(file=file, user=user)
        if not created and access.is_expired():
            if real_renew:
                access.expires = gen_expires()
                await access.save(update_fields=["expires"])
            else:
                await access.delete()
                access = await models.FileAccess.create(file=file, user=user)

        return access
