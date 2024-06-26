from __future__ import annotations

from time import time

from tortoise import fields

from piltover.db.models._utils import Model


def gen_expires() -> int:
    return int(time()) + 60 * 60 * 6  # +6 hours


class AuthKey(Model):
    id: str = fields.CharField(pk=True, max_length=64)
    auth_key: bytes = fields.BinaryField()

    @classmethod
    async def get_or_temp(cls, key_id: int) -> AuthKey:
        if (key := await AuthKey.get_or_none(id=str(key_id))) is not None:
            return key
        return await TempAuthKey.get_or_none(id=str(key_id), expires__gt=int(time())).select_related("perm_key")


class TempAuthKey(Model):
    id: str = fields.CharField(pk=True, max_length=64)
    auth_key: bytes = fields.BinaryField()
    expires: int = fields.BigIntField(default=gen_expires)
    perm_key: AuthKey = fields.ForeignKeyField("models.AuthKey", unique=True, null=True)
