from __future__ import annotations

from typing import cast

from tortoise import fields, Model

from piltover.db import models
from piltover.db.enums import PeerType
from piltover.tl import PeerNotifySettings
from piltover.tl.types import Dialog as TLDialog


class Dialog(Model):
    id: int = fields.BigIntField(pk=True)
    pinned_index: int = fields.SmallIntField(null=True, default=None)
    unread_mark: bool = fields.BooleanField(default=False)

    peer: models.Peer = fields.ForeignKeyField("models.Peer", unique=True)
    draft: fields.ReverseRelation[models.MessageDraft]

    async def to_tl(self) -> TLDialog:
        in_read_state, _ = await models.ReadState.get_or_create(dialog=self, defaults={"last_message_id": 0})
        unread_count = await models.Message.filter(peer=self.peer, id__gt=in_read_state.last_message_id).count()

        out_read_max_id = 0
        if self.peer.type is PeerType.SELF:
            out_read_max_id = in_read_state.last_message_id
        elif self.peer.type is PeerType.USER:
            out_read_state = await models.ReadState.get_or_none(
                dialog__peer__owner__id=self.peer.user_id, dialog__peer__user__id=self.peer.owner_id
            )
            out_read_max_id = out_read_state.last_message_id if out_read_state is not None else 0
        elif self.peer.type is PeerType.CHAT:
            out_read_state = await models.ReadState.filter(
                dialog__peer__chat__id=self.peer.chat_id, dialog__id__not=self.id
            ).order_by("-last_message_id").first()
            if out_read_state:
                out_read_max_id = await models.Message.filter(
                    peer=self.peer, id__lte=out_read_state.last_message_id
                ).order_by("-id").first().values_list("id", flat=True)
                out_read_max_id = out_read_max_id or 0

        defaults = {
            "view_forum_as_messages": False,
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
            read_inbox_max_id=in_read_state.last_message_id,
            read_outbox_max_id=out_read_max_id or 0,
            unread_count=unread_count,
        )
