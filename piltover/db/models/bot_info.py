from __future__ import annotations

from tortoise import Model, fields

from piltover.cache import Cache
from piltover.db import models
from piltover.tl.types import BotInfo as TLBotInfo


class BotInfo(Model):
    id: int = fields.BigIntField(primary_key=True)
    user: models.User = fields.OneToOneField("models.User")
    description: str | None = fields.CharField(max_length=128, null=True, default=None)
    description_photo: models.File | None = fields.ForeignKeyField("models.File", null=True, default=None)
    # TODO: description_document
    privacy_policy_url: str | None = fields.CharField(max_length=240, null=True, default=None)
    version: int = fields.IntField(default=1)

    user_id: int
    description_photo_id: int | None

    def _cache_key(self) -> str:
        return f"bot-info:{self.user_id}:{self.version}"

    async def to_tl(self) -> TLBotInfo:
        if (cached := await Cache.obj.get(self._cache_key())) is not None:
            return cached

        commands = await models.BotCommand.filter(bot_id=self.user_id)

        result = TLBotInfo(
            user_id=self.user_id,
            description=self.description,
            description_photo=self.description_photo.to_tl_photo() if self.description_photo_id is not None else None,
            commands=[
                command.to_tl()
                for command in commands
            ],
            privacy_policy_url=self.privacy_policy_url,
        )

        await Cache.obj.set(self._cache_key(), result)
        return result
