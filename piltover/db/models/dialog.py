from __future__ import annotations

from typing import cast, Iterable, Self

from loguru import logger
from pypika_tortoise import Dialects, Parameter
from tortoise import fields, Tortoise
from tortoise.functions import Count
from tortoise.queryset import QuerySet
from tortoise.transactions import in_transaction

from piltover.db import models
from piltover.db.enums import DialogFolderId, PeerType
from piltover.db.models.dialog_base import DialogBase, DialogBaseT
from piltover.db.models.peer import peer_is_channel_min, peer_is_chat_min
from piltover.exceptions import Unreachable
from piltover.tl.base import InputUser as TLInputUserBase, InputPeer as TLInputPeerBase, \
    InputChannel as TLInputChannelBase
from piltover.tl.types import Dialog as TLDialog


_UNREAD_COUNTS_SQL = """
SELECT
    dialog.id dialog_id, COUNT(mref.id) count
FROM dialog
    JOIN messageref mref on dialog.peer_id = mref.peer_id and mref.id > dialog.last_read_message_id and mref.scheduled_by_user_id is null
WHERE dialog.id {state_condition}
GROUP BY dialog_id
;
"""


class Dialog(DialogBase):
    unread_mark: bool = fields.BooleanField(default=False)
    folder_id: DialogFolderId = fields.IntEnumField(DialogFolderId, default=DialogFolderId.ALL, description="")
    visible: bool = fields.BooleanField(default=True)
    last_read_message_id: int = fields.BigIntField(default=0)

    class Meta:
        unique_together = (
            ("owner_id", "peer_id"),
        )
        indexes = (
            ("owner_id", "folder_id", "pinned_index", "visible"),
        )

    @classmethod
    def top_message_query_bulk(
            cls, user_id: int, dialogs: list[Self], prefetch: bool = True,
    ) -> QuerySet[models.MessageRef]:
        if not dialogs:
            return models.MessageRef.filter(id=0)

        return models.MessageRef.filter(
            id__in=[dialog.peer.last_message_id for dialog in dialogs if dialog.peer.last_message_id is not None]
        ).select_related(
            *(models.MessageRef.PREFETCH_MAYBECACHED if prefetch else ()),
        )

    @classmethod
    async def _get_in_out_ids_and_unread_bulk(
            cls, user_id: int, dialogs: list[Dialog], no_reactions: bool = False, no_mentions: bool = False,
    ) -> list[tuple[int, int, int, int, int]]:
        if not dialogs:
            return []

        fetch_unreads_for = []
        for dialog in dialogs:
            if (dialog.peer.last_message_id or 0) > dialog.last_read_message_id:
                fetch_unreads_for.append(dialog.id)

        unread_by_dialog = {}
        if fetch_unreads_for:
            conn = Tortoise.get_connection("default")
            dialect = Dialects(conn.capabilities.dialect)
            placeholder_factory = Parameter.IDX_PLACEHOLDERS[dialect]
            placeholders = [placeholder_factory(i + 1) for i in range(len(fetch_unreads_for))]

            if len(fetch_unreads_for) == 1:
                where_condition = f"= {placeholders[0]}"
            else:
                where_condition = f"IN ({','.join(placeholders)})"

            sql = _UNREAD_COUNTS_SQL.format(state_condition=where_condition)
            _, results = await conn.execute_query(sql, fetch_unreads_for)
            for res in results:
                unread_by_dialog[res["dialog_id"]] = res["count"]

        unread_reactions_by_peer = {}
        if not no_reactions:
            unread_reactions_counts = await models.MessageRef.filter(
                peer_id__in=[dialog.peer_id for dialog in dialogs],
                reactions_unread_author_id=user_id,
            ).group_by(
                "peer_id"
            ).annotate(
                count=Count("id")
            ).values_list("peer_id", "count")
            unread_reactions_by_peer: dict[int, int] = dict(unread_reactions_counts)

        unread_mentions_by_chat = {}
        if not no_mentions:
            unread_target_ids = set()
            for dialog in dialogs:
                if dialog.peer_id not in unread_by_dialog:
                    # If no new messages - there can't be new mentions
                    continue
                if peer_is_channel_min(dialog.peer):
                    unread_target_ids.add(models.Channel.make_id_from(dialog.peer.channel_id))
                elif peer_is_chat_min(dialog.peer):
                    unread_target_ids.add(models.Chat.make_id_from(dialog.peer.chat_id))

            if unread_target_ids:
                mentions = await models.MessageMention.filter(
                    user_id=user_id, unread_target_id__in=unread_target_ids,
                ).group_by(
                    "unread_target_id",
                ).annotate(
                    count=Count("id"),
                ).values_list(
                    "unread_target_id", "count",
                )

                for unread_target_id, count in mentions:
                    unread_mentions_by_chat[unread_target_id] = count

        result = []
        for dialog in dialogs:
            unread_target_id = None
            peer_ = dialog.peer
            if peer_is_chat_min(peer_):
                unread_target_id = models.Chat.make_id_from(peer_.chat_id)
            elif peer_is_channel_min(peer_):
                unread_target_id = models.Channel.make_id_from(peer_.channel_id)
            result.append((
                dialog.last_read_message_id,
                dialog.peer.out_max_read_id,
                unread_by_dialog.get(dialog.id, 0),
                unread_reactions_by_peer.get(dialog.peer_id, 0),
                unread_mentions_by_chat.get(unread_target_id, 0),
            ))

        return result

    @classmethod
    async def get_in_out_ids_and_unread(
            cls, user_id: int, peer_or_dialog: models.Peer | Dialog,
            no_reactions: bool = False, no_mentions: bool = False,
    ) -> tuple[int, int, int, int, int]:
        if isinstance(peer_or_dialog, Dialog):
            peer = peer_or_dialog.peer
            dialog = peer_or_dialog
        else:
            peer = peer_or_dialog
            dialog = await cls.get_or_create_hidden(user_id, peer_or_dialog)

        unread_count = await models.MessageRef.filter(peer=peer, id__gt=dialog.last_read_message_id).count()
        if no_reactions:
            unread_reactions_count = 0
        else:
            unread_reactions_count = await models.MessageRef.filter(
                peer_id=peer.id, reactions_unread_author_id=user_id,
            ).count()

        if not unread_count or no_mentions or peer.type not in (PeerType.CHAT, PeerType.CHANNEL):
            unread_mentions = 0
        else:
            peer_ = peer
            if peer_is_chat_min(peer_):
                unread_target_id = models.Chat.make_id_from(peer_.chat_id)
            elif peer_is_channel_min(peer_):
                unread_target_id = models.Channel.make_id_from(peer_.channel_id)
            else:
                raise Unreachable
            unread_mentions = await models.MessageMention.filter(
                user_id=user_id, unread_target_id=unread_target_id,
            ).count()

        return (
            dialog.last_read_message_id,
            peer.out_max_read_id,
            unread_count,
            unread_reactions_count,
            unread_mentions,
        )

    async def to_tl(self, pts: int | None = None) -> TLDialog:
        in_read_max_id, out_read_max_id, unread_count, unread_reactions, unread_mentions = \
            await self.get_in_out_ids_and_unread(self.owner_id, self)

        logger.trace(
            f"Max read outbox message id is {out_read_max_id} for peer {self.peer_id} for user {self.owner_id}"
        )

        top_message_id = await models.MessageRef.filter(
            peer_id=self.peer_id
        ).order_by("-id").first().values_list("id", flat=True)
        draft = await models.MessageDraft.get_or_none(user_id=self.owner_id, peer_id=self.peer_id)
        draft = draft.to_tl() if draft else None

        notify_settings = await models.PeerNotifySettings.get_or_none(user_id=self.owner_id, peer_id=self.peer_id)
        notify_settings_tl = models.PeerNotifySettings.DEFAULT_TL
        if notify_settings is not None:
            notify_settings_tl = notify_settings.to_tl()

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
            notify_settings=notify_settings_tl,

            view_forum_as_messages=False,
        )

    @classmethod
    async def to_tl_bulk(
            cls, user_id: int, dialogs: list[Dialog], messages: dict[int, tuple[Dialog, models.MessageRef | None]],
    ) -> list[TLDialog]:
        if not dialogs:
            return []

        peer_ids = [dialog.peer_id for dialog in dialogs]

        drafts = {
            draft.peer_id: draft
            for draft in await models.MessageDraft.filter(user_id=user_id, peer_id__in=peer_ids)
        }

        read_states = await cls._get_in_out_ids_and_unread_bulk(user_id, dialogs)

        notify_settings = {
            settings.peer_id: settings
            for settings in await models.PeerNotifySettings.filter(user_id=user_id, peer_id__in=peer_ids)
        }

        tl = []
        for dialog, read_state in zip(dialogs, read_states):
            top_message = 0
            peer_id = dialog.peer_id
            if peer_id in messages and (peer_message := messages[peer_id][1]) is not None:
                top_message = peer_message.id

            draft = None
            if peer_id in drafts:
                draft = drafts[peer_id].to_tl()

            in_read_max_id, out_read_max_id, unread_count, unread_reactions, unread_mentions = read_state
            this_notify_settings_tl = models.PeerNotifySettings.DEFAULT_TL
            if peer_id in notify_settings:
                this_notify_settings_tl = notify_settings[peer_id].to_tl()

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
                notify_settings=this_notify_settings_tl,

                view_forum_as_messages=False,
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
