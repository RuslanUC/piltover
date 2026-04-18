from __future__ import annotations

from tortoise import Model, fields

from piltover.db import models
from piltover.exceptions import Unreachable
from piltover.tl import ReactionEmoji, ReactionCustomEmoji
from piltover.tl.base import Reaction as TLReaction


class UserReactionsSettings(Model):
    id: int = fields.BigIntField(primary_key=True)
    user: models.User = fields.OneToOneField("models.User")
    default_reaction: models.Reaction | None = fields.ForeignKeyField("models.Reaction", null=True, default=None)
    default_custom_emoji: models.File | None = fields.ForeignKeyField("models.File", null=True, default=None)

    user_id: int
    default_reaction_id: int | None
    default_custom_emoji_id: int | None

    def to_tl_reaction(self) -> TLReaction:
        if self.default_reaction_id is not None:
            return ReactionEmoji(emoticon=self.default_reaction.reaction)
        elif self.default_custom_emoji_id is not None:
            return ReactionCustomEmoji(document_id=self.default_custom_emoji_id)

        raise Unreachable

