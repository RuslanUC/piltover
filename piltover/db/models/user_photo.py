from __future__ import annotations

from tortoise import fields

from piltover.db import models
from piltover.db.models._utils import Model
from piltover.tl_new import Photo as TLPhoto


class UserPhoto(Model):
    id: int = fields.BigIntField(pk=True)
    current: bool = fields.BooleanField(default=False)
    file: models.File = fields.ForeignKeyField("models.File", on_delete=fields.CASCADE)
    user: models.User = fields.ForeignKeyField("models.User", on_delete=fields.CASCADE)

    async def to_tl(self, user: models.User) -> TLPhoto:
        photo = await self.file.to_tl_photo(user)
        photo.id = self.id
        return photo
