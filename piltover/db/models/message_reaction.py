from __future__ import annotations

from datetime import datetime

from tortoise import fields, Model

from piltover.db import models
from piltover.exceptions import Unreachable
from piltover.tl import PeerUser, MessagePeerReaction, ReactionEmoji, ReactionCustomEmoji


class MessageReaction(Model):
    id: int = fields.BigIntField(pk=True)
    user: models.User = fields.ForeignKeyField("models.User")
    message: models.MessageContent = fields.ForeignKeyField("models.MessageContent")
    reaction: models.Reaction | None = fields.ForeignKeyField("models.Reaction", null=True, default=None)
    custom_emoji: models.File | None = fields.ForeignKeyField("models.File", null=True, default=None)
    date: datetime = fields.DatetimeField(auto_now_add=True)

    user_id: int
    message_id: int
    reaction_id: int | None
    custom_emoji_id: int | None

    class Meta:
        unique_together = (
            ("user", "message",),
        )

    def to_tl_peer_reaction(self, user_id: int, last_read_id: int) -> MessagePeerReaction:
        if self.reaction_id is not None:
            reaction = ReactionEmoji(emoticon=self.reaction.reaction)
        elif self.custom_emoji_id is not None:
            reaction = ReactionCustomEmoji(document_id=self.custom_emoji_id)
        else:
            raise Unreachable

        return MessagePeerReaction(
            big=False,
            unread=self.id > last_read_id,
            my=self.user_id == user_id,
            peer_id=PeerUser(user_id=self.user_id),
            date=int(self.date.timestamp()),
            reaction=reaction,
        )
