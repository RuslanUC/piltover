from __future__ import annotations

from time import time
from typing import cast

from tortoise import fields, Model

from piltover.auth_data import AuthData


class AuthKey(Model):
    id: int = fields.BigIntField(primary_key=True)
    auth_key: bytes = fields.BinaryField()
    layer: int = fields.SmallIntField(default=133)

    @classmethod
    async def get_temp_id(cls, key_id: int) -> int | None:
        return cast(int | None, await TempAuthKey.filter(perm_key_id=key_id).first().values_list("id", flat=True))

    @classmethod
    async def get_temp_ids_bulk(cls, key_ids: list[int]) -> list[int]:
        return await TempAuthKey.filter(perm_key_id__in=key_ids).values_list("id", flat=True)

    @classmethod
    async def get_auth_data(cls, key_id: int) -> AuthData | None:
        if (key := await AuthKey.get_or_none(id=key_id).only("id", "auth_key")) is not None:
            return AuthData(
                auth_key_id=key.id,
                auth_key=key.auth_key,
                perm_auth_key_id=key.id
            )

        temp_key = await TempAuthKey.get_or_none(
            id=key_id, expires_at__gt=int(time()),
        ).only("id", "auth_key", "perm_key_id")
        if temp_key is not None:
            return AuthData(
                auth_key_id=temp_key.id,
                auth_key=temp_key.auth_key,
                perm_auth_key_id=temp_key.perm_key_id,
            )


class TempAuthKey(Model):
    id: int = fields.BigIntField(primary_key=True)
    auth_key: bytes = fields.BinaryField()
    expires_at: int = fields.BigIntField()
    perm_key: AuthKey | None = fields.OneToOneField("models.AuthKey", null=True)

    perm_key_id: int | None
