from __future__ import annotations

from tortoise import fields, Model

from piltover.db import models
from piltover.tl import EncryptedFile as TLEncryptedFile


class EncryptedFile(Model):
    id: int = fields.BigIntField(pk=True)
    file: models.File = fields.ForeignKeyField("models.File")
    key_fingerprint: int = fields.BigIntField()

    file_id: int

    # TODO: remove user
    # TODO: remove async
    async def to_tl(self, user: models.User) -> TLEncryptedFile:
        return TLEncryptedFile(
            id=self.file.id,
            access_hash=-1,
            size=self.file.size,
            dc_id=2,
            key_fingerprint=self.key_fingerprint,
        )
