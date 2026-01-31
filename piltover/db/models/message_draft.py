from __future__ import annotations

from datetime import datetime

from tortoise import fields, Model

from piltover.db import models
from piltover.db.models.utils import NullableFKSetNull
from piltover.tl import DraftMessage, InputReplyToMessage, objects


class MessageDraft(Model):
    id: int = fields.BigIntField(pk=True)
    message: str = fields.TextField()
    date: datetime = fields.DatetimeField(default=datetime.now)
    peer: models.Peer = fields.OneToOneField("models.Peer")
    reply_to: models.MessageRef | None = NullableFKSetNull("models.MessageRef")
    no_webpage: bool = fields.BooleanField(default=False)
    invert_media: bool = fields.BooleanField(default=False)
    # TODO: use tl for entities
    entities: list[dict] | None = fields.JSONField(null=True, default=None)

    peer_id: int
    reply_to_id: int | None

    def to_tl(self) -> DraftMessage:
        entities = []
        for entity in (self.entities or []):
            tl_id = entity.pop("_")
            entities.append(objects[tl_id](**entity))
            entity["_"] = tl_id

        return DraftMessage(
            message=self.message,
            date=int(self.date.timestamp()),
            reply_to=InputReplyToMessage(reply_to_msg_id=self.reply_to_id) if self.reply_to_id is not None else None,
            no_webpage=self.no_webpage,
            invert_media=self.invert_media,
            entities=entities if entities else None,
        )
