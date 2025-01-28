from __future__ import annotations

from tortoise import fields, Model

from piltover.db import models
from piltover.tl.types import SavedDialog as TLSavedDialog


class SavedDialog(Model):
    id: int = fields.BigIntField(pk=True)
    peer: models.Peer = fields.ForeignKeyField("models.Peer", unique=True)

    async def to_tl(self) -> TLSavedDialog:
        top_message_id = await models.Message.filter(peer=self.peer).order_by("-id").first().values_list("id", flat=True)
        top_message_id = top_message_id or 0

        return TLSavedDialog(
            pinned=False,
            peer=self.peer.to_tl(),
            top_message=top_message_id,
        )
