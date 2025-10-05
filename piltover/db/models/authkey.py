from __future__ import annotations

from time import time
from typing import cast

from tortoise import fields, Model


class AuthKey(Model):
    id: int = fields.BigIntField(pk=True)
    auth_key: bytes = fields.BinaryField()
    layer: int = fields.SmallIntField(default=133)

    @classmethod
    async def get_or_temp(cls, key_id: int) -> AuthKey | TempAuthKey:
        if (key := await AuthKey.get_or_none(id=key_id)) is not None:
            return key
        return await TempAuthKey.get_or_none(id=key_id, expires_at__gt=int(time())).select_related("perm_key")

    async def get_ids(self) -> list[int]:
        ids = [self.id]
        if (temp_id := await TempAuthKey.filter(perm_key=self).first().values_list("id", flat=True)) is not None:
            ids.append(temp_id)

        return ids


class TempAuthKey(Model):
    id: int = fields.BigIntField(pk=True)
    auth_key: bytes = fields.BinaryField()
    expires_at: int = fields.BigIntField()
    perm_key: AuthKey | None = fields.ForeignKeyField("models.AuthKey", unique=True, null=True)
