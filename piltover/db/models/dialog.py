from __future__ import annotations

from typing import cast, Iterable

from loguru import logger
from tortoise import fields, Model
from tortoise.expressions import Q
from tortoise.queryset import QuerySetSingle
from tortoise.transactions import in_transaction

from piltover.db import models
from piltover.db.enums import DialogFolderId, PeerType
from piltover.tl import PeerNotifySettings
from piltover.tl.types import Dialog as TLDialog


class Dialog(Model):
    id: int = fields.BigIntField(pk=True)
    pinned_index: int | None = fields.SmallIntField(null=True, default=None)
    unread_mark: bool = fields.BooleanField(default=False)
    folder_id: DialogFolderId = fields.IntEnumField(DialogFolderId, default=DialogFolderId.ALL)
    visible: bool = fields.BooleanField(default=True)

    peer: models.Peer = fields.OneToOneField("models.Peer")

    peer_id: int

    def top_message_query(self, prefetch: bool = True) -> QuerySetSingle[models.Message]:
        if self.peer.type is PeerType.CHANNEL:
            top_message_q = Q(peer=self.peer) | Q(peer__owner=None, peer__channel__id=self.peer.channel_id)
        else:
            top_message_q = Q(peer=self.peer)

        return models.Message.filter(top_message_q).select_related(
            *(models.Message.PREFETCH_FIELDS if prefetch else ()),
        ).order_by("-id").first()

    async def to_tl(self) -> TLDialog:
        in_read_max_id, out_read_max_id, unread_count, unread_reactions, unread_mentions = \
            await models.ReadState.get_in_out_ids_and_unread(self.peer)

        logger.trace(
            f"Max read outbox message id is {out_read_max_id} for peer {self.peer.id} for user {self.peer.owner_id}"
        )

        top_message = await self.top_message_query(False).values_list("id", flat=True)
        draft = await models.MessageDraft.get_or_none(peer=self.peer)
        draft = draft.to_tl() if draft else None

        return TLDialog(
            pinned=self.pinned_index is not None,
            unread_mark=self.unread_mark,
            peer=self.peer.to_tl(),
            top_message=cast(int | None, top_message) or 0,
            draft=draft,
            read_inbox_max_id=in_read_max_id,
            read_outbox_max_id=out_read_max_id,
            unread_count=unread_count,
            unread_reactions_count=unread_reactions,
            folder_id=self.folder_id.value,
            unread_mentions_count=unread_mentions,
            ttl_period=self.peer.user_ttl_period_days * 86400 if self.peer.user_ttl_period_days else None,

            view_forum_as_messages=False,
            notify_settings=PeerNotifySettings(),
        )

    @classmethod
    async def create_or_unhide(cls, peer: models.Peer) -> Dialog:
        dialog, _ = await cls.update_or_create(peer=peer, defaults={"visible": True})
        return dialog

    @classmethod
    async def hide(cls, peer: models.Peer) -> Dialog:
        dialog, _ = await cls.update_or_create(peer=peer, defaults={"visible": False})
        return dialog

    @classmethod
    async def get_or_create_hidden(cls, peer: models.Peer) -> Dialog:
        dialog, _ = await cls.get_or_create(peer=peer, defaults={"visible": False})
        return dialog

    @classmethod
    async def create_or_unhide_bulk(cls, peers: Iterable[models.Peer]) -> None:
        valid_peers = [peer for peer in peers if peer.owner_id is not None]

        if not valid_peers:
            return

        async with in_transaction():
            existing = {
                dialog.peer_id: dialog
                for dialog in await cls.select_for_update().filter(peer__id__in=[peer.id for peer in valid_peers])
            }

            to_create = [cls(peer=peer, visible=True) for peer in valid_peers if peer.id not in existing]
            to_update = [dialog for dialog in existing.values() if not dialog.visible]
            for dialog in to_update:
                dialog.visible = True

            if to_create:
                await cls.bulk_create(to_create)
            if to_update:
                await cls.bulk_update(to_update, fields=["visible"])

