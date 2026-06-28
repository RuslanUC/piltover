from __future__ import annotations

from typing import cast, Iterable

from loguru import logger
from tortoise import fields
from tortoise.queryset import QuerySet
from tortoise.transactions import in_transaction

from piltover.db import models
from piltover.db.enums import DialogFolderId
from piltover.db.models.dialog_base import DialogBase, DialogBaseT
from piltover.tl import PeerNotifySettings
from piltover.tl.base import InputUser as TLInputUserBase, InputPeer as TLInputPeerBase, \
    InputChannel as TLInputChannelBase
from piltover.tl.types import Dialog as TLDialog


class Dialog(DialogBase):
    unread_mark: bool = fields.BooleanField(default=False)
    folder_id: DialogFolderId = fields.IntEnumField(DialogFolderId, default=DialogFolderId.ALL, description="")
    visible: bool = fields.BooleanField(default=True)

    class Meta:
        unique_together = (
            ("owner_id", "peer_id"),
        )
        indexes = (
            ("owner_id", "folder_id", "pinned_index", "visible"),
        )

    @classmethod
    def top_message_query_bulk(
            cls, _: int, dialogs: list[Dialog], prefetch: bool = True,
    ) -> QuerySet[models.MessageRef]:
        if not dialogs:
            return models.MessageRef.filter(id=0)

        return models.MessageRef.filter(
            id__in=[dialog.peer.last_message_id for dialog in dialogs if dialog.peer.last_message_id is not None]
        ).select_related(
            *(models.MessageRef.PREFETCH_MAYBECACHED if prefetch else ()),
        )

    async def to_tl(self, pts: int | None = None) -> TLDialog:
        in_read_max_id, out_read_max_id, unread_count, unread_reactions, unread_mentions = \
            await models.ReadState.get_in_out_ids_and_unread(self.owner_id, self.peer)

        logger.trace(
            f"Max read outbox message id is {out_read_max_id} for peer {self.peer_id} for user {self.owner_id}"
        )

        top_message_id = await models.MessageRef.filter(
            peer_id=self.peer_id
        ).order_by("-id").first().values_list("id", flat=True)
        draft = await models.MessageDraft.get_or_none(user_id=self.owner_id, peer_id=self.peer_id)
        draft = draft.to_tl() if draft else None

        return TLDialog(
            pinned=self.pinned_index is not None,
            unread_mark=self.unread_mark,
            peer=self.peer.to_tl(),
            top_message=cast(int | None, cast(object, top_message_id)) or 0,
            draft=draft,
            read_inbox_max_id=in_read_max_id,
            read_outbox_max_id=out_read_max_id,
            unread_count=unread_count,
            unread_reactions_count=unread_reactions,
            folder_id=self.folder_id.value,
            unread_mentions_count=unread_mentions,
            ttl_period=self.peer.user_ttl_period_days * 86400 if self.peer.user_ttl_period_days else None,
            pts=pts,

            view_forum_as_messages=False,
            notify_settings=PeerNotifySettings(),
        )

    @classmethod
    async def to_tl_bulk(
            cls, user_id: int, dialogs: list[Dialog], messages: dict[int, tuple[Dialog, models.MessageRef | None]],
    ) -> list[TLDialog]:
        if not dialogs:
            return []

        drafts = {
            draft.peer_id: draft
            for draft in await models.MessageDraft.filter(
                user_id=user_id, peer_id__in=[dialog.peer_id for dialog in dialogs]
            )
        }

        read_states = await models.ReadState.get_in_out_ids_and_unread_bulk(
            user_id, [dialog.peer for dialog in dialogs],
        )

        tl = []
        for dialog, read_state in zip(dialogs, read_states):
            top_message = 0
            peer_id = dialog.peer_id
            if peer_id in messages and (peer_message := messages[peer_id][1]) is not None:
                top_message = peer_message.id

            draft = None
            if dialog.peer_id in drafts:
                draft = drafts[dialog.peer_id].to_tl()

            in_read_max_id, out_read_max_id, unread_count, unread_reactions, unread_mentions = read_state

            # TODO: include pts if peer is channel
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
    async def create_or_unhide(cls, user_id: int, peer: models.Peer) -> Dialog:
        dialog, _ = await cls.update_or_create(owner_id=user_id, peer=peer, defaults={"visible": True})
        return dialog

    @classmethod
    async def hide(cls, user_id: int, peer: models.Peer) -> Dialog:
        dialog, _ = await cls.update_or_create(owner_id=user_id, peer=peer, defaults={"visible": False})
        return dialog

    @classmethod
    async def get_or_create_hidden(cls, user_id: int, peer: models.Peer) -> Dialog:
        dialog, _ = await cls.get_or_create(owner_id=user_id, peer=peer, defaults={"visible": False})
        return dialog

    @classmethod
    async def create_or_unhide_bulk(cls, peers: Iterable[models.Peer]) -> None:
        valid_peers = [peer for peer in peers if peer.owner_id is not None]
        peer_owner_ids = [peer.owner_id for peer in valid_peers]
        peer_ids = [peer.id for peer in valid_peers]

        if not valid_peers:
            return

        async with in_transaction():
            existing = {
                dialog.peer_id: dialog
                for dialog in await cls.select_for_update().filter(owner_id__in=peer_owner_ids, peer_id__in=peer_ids)
            }

            to_create = [
                cls(owner_id=peer.owner_id, peer=peer, visible=True)
                for peer in valid_peers
                if peer.id not in existing
            ]
            to_update = [dialog for dialog in existing.values() if not dialog.visible]
            for dialog in to_update:
                dialog.visible = True

            if to_create:
                await cls.bulk_create(to_create)
            if to_update:
                await cls.bulk_update(to_update, fields=["visible"])

    @classmethod
    def get_from_input_peer(
            cls: type[DialogBaseT], user_id: int, input_peer: TLInputPeerBase | TLInputUserBase | TLInputChannelBase,
            error_message: str = "PEER_ID_INVALID",
    ) -> QuerySet[DialogBaseT]:
        query = super().get_from_input_peer(user_id, input_peer, error_message)
        return query.filter(visible=True)

    @classmethod
    def get_from_input_peer_many(
            cls: type[DialogBaseT], user_id: int,
            input_peers: list[TLInputPeerBase | TLInputUserBase | TLInputChannelBase],
    ) -> QuerySet[DialogBaseT]:
        query = super().get_from_input_peer_many(user_id, input_peers)
        return query.filter(visible=True)
