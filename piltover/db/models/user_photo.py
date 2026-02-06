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
        return self.file.to_tl_photo()

    def to_tl_profile(self) -> UserProfilePhoto:
        return UserProfilePhoto(
            photo_id=self.file_id,
            dc_id=2,
            stripped_thumb=self.file.photo_stripped,
        )
