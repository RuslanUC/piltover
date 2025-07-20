from __future__ import annotations

from time import time
from typing import cast

from tortoise import fields, Model


class AuthKey(Model):
    id: str = fields.CharField(pk=True, max_length=64)
    auth_key: bytes = fields.BinaryField()

    @classmethod
    async def get_or_temp(cls, key_id: int) -> AuthKey | TempAuthKey:
        if (key := await AuthKey.get_or_none(id=str(key_id))) is not None:
            return key
        return await TempAuthKey.get_or_none(id=str(key_id), expires_at__gt=int(time())).select_related("perm_key")

    async def get_ids(self) -> list[int]:
        ids = [int(self.id)]
        if (temp_id := await TempAuthKey.filter(perm_key=self).first().values_list("id", flat=True)) is not None:
            ids.append(int(cast(str, temp_id)))

        return ids


class TempAuthKey(Model):
    id: str = fields.CharField(pk=True, max_length=64)
    auth_key: bytes = fields.BinaryField()
    expires_at: int = fields.BigIntField()
    perm_key: AuthKey | None = fields.ForeignKeyField("models.AuthKey", unique=True, null=True)
