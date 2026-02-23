from __future__ import annotations

from datetime import datetime

from fastrand import xorshift128plus_bytes
from tortoise import fields, Model

from piltover.db import models
from piltover.tl import Long


def qr_gen_nonce() -> int:
    return Long.read_bytes(xorshift128plus_bytes(8), signed=True)


class QrLogin(Model):
    EXPIRE_TIME = 30

    id: int = fields.BigIntField(pk=True)
    created_at: datetime = fields.DatetimeField(auto_now_add=True)
    key: models.AuthKey = fields.ForeignKeyField("models.AuthKey")
    nonce: int = fields.BigIntField(default=qr_gen_nonce)
    auth: models.UserAuthorization | None = fields.ForeignKeyField("models.UserAuthorization", null=True, default=None)

    auth_id: int | None

    def to_token(self) -> bytes:
        return Long.write(self.id) + Long.write(self.nonce)

    @classmethod
    async def from_token(cls, token: bytes) -> QrLogin | None:
        if len(token) != 16:
            return None

        login_id = Long.read_bytes(token[:8])
        nonce = Long.read_bytes(token[8:])

        return await cls.get_or_none(id=login_id, nonce=nonce).select_related("key")
