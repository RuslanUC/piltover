from __future__ import annotations

from tortoise import fields, Model

from piltover.db import models
from piltover.tl import EncryptedFile as TLEncryptedFile


class EncryptedFile(Model):
    id: int = fields.BigIntField(pk=True)
    file: models.File = fields.ForeignKeyField("models.File")
    key_fingerprint: int = fields.BigIntField()

    file_id: int

    async def to_tl(self, user: models.User) -> TLEncryptedFile:
        access, _ = await models.FileAccess.get_or_create(file=self.file, user=user, defaults={"expires": None})
        return TLEncryptedFile(
            id=self.file.id,
            access_hash=access.access_hash,
            size=self.file.size,
            dc_id=2,
            key_fingerprint=self.key_fingerprint,
        )
