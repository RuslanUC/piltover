from __future__ import annotations

from time import time

from tortoise import fields, Model


class AuthKey(Model):
    id: str = fields.CharField(pk=True, max_length=64)
    auth_key: bytes = fields.BinaryField()

    @classmethod
    async def get_or_temp(cls, key_id: int) -> AuthKey | TempAuthKey:
        if (key := await AuthKey.get_or_none(id=str(key_id))) is not None:
            return key
        return await TempAuthKey.get_or_none(id=str(key_id), expires_at__gt=int(time())).select_related("perm_key")


class TempAuthKey(Model):
    id: str = fields.CharField(pk=True, max_length=64)
    auth_key: bytes = fields.BinaryField()
    expires_at: int = fields.BigIntField()
    perm_key: AuthKey | None = fields.ForeignKeyField("models.AuthKey", unique=True, null=True)
