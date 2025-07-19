from __future__ import annotations

from datetime import datetime

from tortoise import fields, Model
from tortoise.transactions import in_transaction

from piltover.db import models


class RecentReaction(Model):
    id: int = fields.BigIntField(pk=True)
    user: models.User = fields.ForeignKeyField("models.User")
    reaction: models.Reaction = fields.ForeignKeyField("models.Reaction")
    used_at: datetime = fields.DatetimeField(auto_now_add=True)

    reaction_id: int

    @classmethod
    async def update_time_or_create(
            cls, user: models.User, reaction: models.Reaction, time: datetime,
    ) -> tuple[RecentReaction, bool]:
        async with in_transaction() as connection:
            instance = await cls.select_for_update().using_db(connection).get_or_none(user=user, reaction=reaction)
            if instance:
                instance.used_at = time
                await instance.save(update_fields=["used_at"], using_db=connection)
                return instance, False
        return await cls.get_or_create(user=user, reaction=reaction, defaults={"used_at": time})
