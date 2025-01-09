from __future__ import annotations

from typing import cast

from tortoise import fields, Model

from piltover.db import models
from piltover.tl import PeerNotifySettings
from piltover.tl.types import Dialog as TLDialog


class Dialog(Model):
    id: int = fields.BigIntField(pk=True)
    pinned_index: int = fields.SmallIntField(null=True, default=None)
    unread_mark: bool = fields.BooleanField(default=False)

    peer: models.Peer = fields.ForeignKeyField("models.Peer", unique=True)
    draft: fields.ReverseRelation[models.MessageDraft]

    async def to_tl(self) -> TLDialog:
        read_state, _ = await models.ReadState.get_or_create(dialog=self, defaults={"last_message_id": 0})
        unread_count = await models.Message.filter(peer=self.peer, id__gt=read_state.last_message_id).count()

        defaults = {
            "view_forum_as_messages": False,
            "read_outbox_max_id": 0,  # TODO
            "unread_mentions_count": 0,
            "unread_reactions_count": 0,
            "notify_settings": PeerNotifySettings(),
        }

        top_message = await models.Message.filter(peer=self.peer).order_by("-id").first().values_list("id", flat=True)
        draft = await models.MessageDraft.get_or_none(dialog=self)
        draft = draft.to_tl() if draft else None

        return TLDialog(
            **defaults,
            pinned=self.pinned_index is not None,
            unread_mark=self.unread_mark,
            peer=self.peer.to_tl(),
            top_message=cast(int, top_message),
            draft=draft,
            read_inbox_max_id=read_state.last_message_id,
            unread_count=unread_count,
        )
