from __future__ import annotations

from time import time

from tortoise import fields, Model

from piltover.auth_data import AuthData


class AuthKey(Model):
    id: int = fields.BigIntField(pk=True)
    auth_key: bytes = fields.BinaryField()
    layer: int = fields.SmallIntField(default=133)

    async def get_ids(self) -> list[int]:
        ids = [self.id]
        if (temp_id := await TempAuthKey.filter(perm_key=self).first().values_list("id", flat=True)) is not None:
            ids.append(temp_id)

        return ids

    @classmethod
    async def get_auth_data(cls, key_id: int) -> AuthData | None:
        if (key := await AuthKey.get_or_none(id=key_id)) is not None:
            return AuthData(
                auth_key_id=key.id,
                auth_key=key.auth_key,
                perm_auth_key_id=key.id
            )

        temp_key = await TempAuthKey.get_or_none(id=key_id, expires_at__gt=int(time()))
        if temp_key is not None:
            return AuthData(
                auth_key_id=temp_key.id,
                auth_key=temp_key.auth_key,
                perm_auth_key_id=temp_key.perm_key_id,
            )


class TempAuthKey(Model):
    id: int = fields.BigIntField(pk=True)
    auth_key: bytes = fields.BinaryField()
    expires_at: int = fields.BigIntField()
    perm_key: AuthKey | None = fields.OneToOneField("models.AuthKey", null=True)

    perm_key_id: int | None
