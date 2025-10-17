from __future__ import annotations

from tortoise import fields, Model


class AuthKey(Model):
    id: int = fields.BigIntField(pk=True)
    auth_key: bytes = fields.BinaryField()
    layer: int = fields.SmallIntField(default=133)

    async def get_ids(self) -> list[int]:
        ids = [self.id]
        if (temp_id := await TempAuthKey.filter(perm_key=self).first().values_list("id", flat=True)) is not None:
            ids.append(temp_id)

        return ids


class TempAuthKey(Model):
    id: int = fields.BigIntField(pk=True)
    auth_key: bytes = fields.BinaryField()
    expires_at: int = fields.BigIntField()
    perm_key: AuthKey | None = fields.OneToOneField("models.AuthKey", null=True)
