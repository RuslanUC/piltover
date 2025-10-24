from __future__ import annotations

from tortoise import fields, Model
from tortoise.queryset import QuerySetSingle

from piltover.db import models
from piltover.tl.types import SavedDialog as TLSavedDialog


class SavedDialog(Model):
    id: int = fields.BigIntField(pk=True)
    pinned_index: int | None = fields.SmallIntField(null=True, default=None)
    peer: models.Peer = fields.OneToOneField("models.Peer")

    def top_message_query(self) -> QuerySetSingle[models.Message]:
        # TODO: this will load top message in chat with `self.peer`, not top saved message from `self.peer`
        return models.Message.filter(peer=self.peer).select_related("author", "peer").order_by("-id").first()

    async def to_tl(self) -> TLSavedDialog:
        top_message_id = await self.top_message_query().values_list("id", flat=True)
        top_message_id = top_message_id or 0

        return TLSavedDialog(
            pinned=False,
            peer=self.peer.to_tl(),
            top_message=top_message_id,
        )
