from __future__ import annotations

from datetime import datetime, timedelta
from os import urandom
from time import mktime

from tortoise import fields

from piltover.db import models
from piltover.db.models._utils import Model
from piltover.tl_new import Photo as TLPhoto, PhotoSize


def gen_access_hash() -> int:
    return int.from_bytes(urandom(7))


def gen_file_reference() -> bytes:
    return urandom(16)


def gen_expires() -> datetime:
    return datetime.now() + timedelta(days=7)


class UserPhoto(Model):
    id: int = fields.BigIntField(pk=True)
    current: bool = fields.BooleanField(default=gen_access_hash)
    file: models.File = fields.ForeignKeyField("models.File", on_delete=fields.CASCADE)
    user: models.User = fields.ForeignKeyField("models.User", on_delete=fields.CASCADE)

    async def to_tl(self, current_user: models.User) -> TLPhoto:
        access = await models.FileAccess.get_or_renew(current_user, self.file)

        return TLPhoto(
            id=self.id,
            access_hash=access.access_hash,
            file_reference=access.file_reference,
            date=int(mktime(self.file.created_at.timetuple())),
            sizes=[PhotoSize(**size) for size in self.file.attributes.get("_sizes", [])],
            dc_id=2,
            video_sizes=[],
        )
