from __future__ import annotations

from typing import cast

from tortoise import fields, Model

from piltover.db import models
from piltover.db.enums import DialogFolderId
from piltover.tl import PeerNotifySettings
from piltover.tl.types import Dialog as TLDialog


class Dialog(Model):
    id: int = fields.BigIntField(pk=True)
    pinned_index: int | None = fields.SmallIntField(null=True, default=None)
    unread_mark: bool = fields.BooleanField(default=False)
    folder_id: DialogFolderId = fields.IntEnumField(DialogFolderId, default=DialogFolderId.ALL)

    peer: models.Peer = fields.ForeignKeyField("models.Peer", unique=True)
    draft: fields.ReverseRelation[models.MessageDraft]

    peer_id: int

    async def to_tl(self) -> TLDialog:
        in_read_max_id, out_read_max_id, unread_count, unread_reactions, unread_mentions = \
            await models.ReadState.get_in_out_ids_and_unread(self.peer)

        defaults = {
            "view_forum_as_messages": False,
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
            read_inbox_max_id=in_read_max_id,
            read_outbox_max_id=out_read_max_id,
            unread_count=unread_count,
            unread_reactions_count=unread_reactions,
            folder_id=self.folder_id.value,
            unread_mentions_count=unread_mentions,
        )
