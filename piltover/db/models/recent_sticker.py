from __future__ import annotations

from datetime import datetime, UTC

from tortoise import fields, Model
from tortoise.transactions import in_transaction

from piltover.db import models


class RecentSticker(Model):
    id: int = fields.BigIntField(pk=True)
    user: models.User = fields.ForeignKeyField("models.User")
    sticker: models.File = fields.ForeignKeyField("models.File")
    used_at: datetime = fields.DatetimeField(auto_now_add=True)

    sticker_id: int

    class Meta:
        unique_together = (
            ("user", "sticker"),
        )

    @classmethod
    async def update_time_or_create(
            cls, user: models.User, sticker: models.File, time: datetime | None = None,
    ) -> tuple[RecentSticker, bool]:
        if time is None:
            time = datetime.now(UTC)

        async with in_transaction() as connection:
            instance = await cls.select_for_update().using_db(connection).get_or_none(user=user, sticker=sticker)
            if instance:
                instance.used_at = time
                await instance.save(update_fields=["used_at"], using_db=connection)
                return instance, False
        return await cls.get_or_create(user=user, sticker=sticker, defaults={"used_at": time})
