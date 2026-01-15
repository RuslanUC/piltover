from __future__ import annotations

from tortoise import fields, Model

from piltover.db import models
from piltover.tl import Photo as TLPhoto, UserProfilePhoto


class UserPhoto(Model):
    id: int = fields.BigIntField(pk=True)
    current: bool = fields.BooleanField(default=False)
    fallback: bool = fields.BooleanField(default=False)
    file: models.File = fields.ForeignKeyField("models.File")
    user: models.User = fields.ForeignKeyField("models.User")

    file_id: int
    user_id: int

    def to_tl(self) -> TLPhoto:
        photo = self.file.to_tl_photo()
        photo.id = self.id
        return photo

    def to_tl_profile(self) -> UserProfilePhoto:
        return UserProfilePhoto(
            # TODO: shouldn't it be self.file_id?
            photo_id=self.id,
            dc_id=2,
            stripped_thumb=self.file.photo_stripped,
        )
