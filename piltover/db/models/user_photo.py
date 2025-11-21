from __future__ import annotations

from tortoise import fields, Model

from piltover.db import models
from piltover.tl import Photo as TLPhoto


class UserPhoto(Model):
    id: int = fields.BigIntField(pk=True)
    current: bool = fields.BooleanField(default=False)
    file: models.File = fields.ForeignKeyField("models.File", on_delete=fields.CASCADE)
    user: models.User = fields.ForeignKeyField("models.User", on_delete=fields.CASCADE)

    def to_tl(self, user: models.User) -> TLPhoto:
        photo = self.file.to_tl_photo(user)
        photo.id = self.id
        return photo
