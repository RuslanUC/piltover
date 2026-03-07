from __future__ import annotations

from datetime import datetime

from tortoise import fields, Model
from tortoise.transactions import in_transaction

from piltover.db import models
from piltover.exceptions import Unreachable
from piltover.tl import ReactionEmoji, ReactionCustomEmoji
from piltover.tl.base import Reaction as TLReactionBase


class RecentReaction(Model):
    id: int = fields.BigIntField(pk=True)
    user: models.User = fields.ForeignKeyField("models.User")
    reaction: models.Reaction | None = fields.ForeignKeyField("models.Reaction", null=True, default=None)
    custom_emoji: models.File | None = fields.ForeignKeyField("models.File", null=True, default=None)
    used_at: datetime = fields.DatetimeField(auto_now_add=True)

    reaction_id: int | None
    custom_emoji_id: int | None

    class Meta:
        unique_together = (
            ("user", "reaction"),
            ("user", "custom_emoji"),
        )

    @classmethod
    async def update_time_or_create(
            cls, user: models.User, reaction: models.Reaction | None, custom_emoji: models.File | None,
            time: datetime,
    ) -> tuple[RecentReaction, bool]:
        async with in_transaction() as connection:
            instance = await cls.select_for_update().using_db(connection).get_or_none(
                user=user, reaction=reaction, custom_emoji=custom_emoji,
            )
            if instance:
                instance.used_at = time
                await instance.save(update_fields=["used_at"], using_db=connection)
                return instance, False
        return await cls.get_or_create(user=user, reaction=reaction, custom_emoji=custom_emoji, defaults={
            "used_at": time,
        })

    def to_tl(self) -> TLReactionBase:
        if self.reaction is not None:
            return ReactionEmoji(emoticon=self.reaction.reaction)
        if self.custom_emoji_id is not None:
            return ReactionCustomEmoji(document_id=self.custom_emoji_id)
        raise Unreachable
