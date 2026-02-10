from __future__ import annotations

from typing import cast, Iterable

from loguru import logger
from tortoise import fields, Model
from tortoise.expressions import Q, Subquery
from tortoise.functions import Min
from tortoise.queryset import QuerySetSingle, QuerySet
from tortoise.transactions import in_transaction

from piltover.db import models
from piltover.db.enums import DialogFolderId, PeerType
from piltover.exceptions import Unreachable
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

    def top_message_query(self, prefetch: bool = True) -> QuerySetSingle[models.MessageRef]:
        return models.MessageRef.filter(self.peer.q_this_and_channel()).select_related(
            *(models.MessageRef.PREFETCH_FIELDS if prefetch else ()),
        ).order_by("-id").first()

    @classmethod
    def top_message_query_bulk(
            cls, _: models.User, dialogs: list[Dialog], prefetch: bool = True,
    ) -> QuerySet[models.MessageRef]:
        peers_q = []
        for dialog in dialogs:
            if dialog.peer.type is PeerType.CHANNEL:
                peers_q.append(Q(peer__owner=None, peer__channel__id=dialog.peer.channel_id))
            else:
                peers_q.append(Q(peer__id=dialog.peer_id))

        return models.MessageRef.filter(
            id__in=Subquery(
                models.MessageRef.filter(
                    Q(*peers_q, join_type=Q.OR)
                ).group_by("peer__id").annotate(min_id=Min("id")).values("min_id")
            )
        ).select_related(
            *(models.MessageRef.PREFETCH_FIELDS if prefetch else ()),
        )

    def peer_key(self) -> tuple[PeerType, int]:
        if self.peer.type in (PeerType.SELF, PeerType.USER):
            peer_id = self.peer.user_id
        elif self.peer.type is PeerType.CHAT:
            peer_id = self.peer.chat_id
        elif self.peer.type is PeerType.CHANNEL:
            peer_id = self.peer.channel_id
        else:
            raise Unreachable

        return self.peer.type, peer_id

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
    async def to_tl_bulk(
            cls, dialogs: list[Dialog], messages: dict[tuple[PeerType, int], tuple[Dialog, models.MessageRef | None]],
    ) -> list[TLDialog]:
        drafts = {
            draft.peer_id: draft
            for draft in await models.MessageDraft.filter(peer__id__in=[dialog.peer_id for dialog in dialogs])
        }

        tl = []
        for dialog in dialogs:
            top_message = 0
            peer_key = dialog.peer_key()
            if peer_key in messages and messages[peer_key][1] is not None:
                top_message = messages[peer_key][1].id

            draft = None
            if dialog.peer_id in drafts:
                draft = drafts[dialog.peer_id].to_tl()

            # TODO: add get_in_out_ids_and_unread_bulk
            in_read_max_id, out_read_max_id, unread_count, unread_reactions, unread_mentions = \
                await models.ReadState.get_in_out_ids_and_unread(dialog.peer)

            tl.append(TLDialog(
                pinned=dialog.pinned_index is not None,
                unread_mark=dialog.unread_mark,
                peer=dialog.peer.to_tl(),
                top_message=cast(int | None, top_message) or 0,
                draft=draft,
                read_inbox_max_id=in_read_max_id,
                read_outbox_max_id=out_read_max_id,
                unread_count=unread_count,
                unread_reactions_count=unread_reactions,
                folder_id=dialog.folder_id.value,
                unread_mentions_count=unread_mentions,
                ttl_period=dialog.peer.user_ttl_period_days * 86400 if dialog.peer.user_ttl_period_days else None,

                view_forum_as_messages=False,
                notify_settings=PeerNotifySettings(),
            ))

        return tl

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
