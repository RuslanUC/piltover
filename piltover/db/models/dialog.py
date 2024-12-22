from __future__ import annotations

from tortoise import fields

from piltover.db import models
from piltover.db.models._utils import Model
from piltover.tl import PeerNotifySettings
from piltover.tl.types import Dialog as TLDialog


class Dialog(Model):
    id: int = fields.BigIntField(pk=True)
    pinned_index: int = fields.SmallIntField(null=True, default=None)
    unread_mark: bool = fields.BooleanField(default=False)

    peer: models.Peer = fields.ForeignKeyField("models.Peer", unique=True)
    draft: fields.ReverseRelation[models.MessageDraft]

    async def to_tl(self, **kwargs) -> TLDialog:
        defaults = {
            "view_forum_as_messages": False,
            "read_inbox_max_id": 0,
            "read_outbox_max_id": 0,
            "unread_count": 0,
            "unread_mentions_count": 0,
            "unread_reactions_count": 0,
            "notify_settings": PeerNotifySettings(),
        } | kwargs

        top_message = await models.Message.filter(peer=self.peer).order_by("-id").first()
        draft = await models.MessageDraft.get_or_none(dialog=self)
        draft = draft.to_tl() if draft else None

        return TLDialog(
            **defaults,
            pinned=self.pinned_index is not None,
            unread_mark=self.unread_mark,
            peer=self.peer.to_tl(),
            top_message=top_message.id if top_message is not None else 0,
            draft=draft,
        )
