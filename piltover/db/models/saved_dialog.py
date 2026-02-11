from __future__ import annotations

from tortoise import fields, Model
from tortoise.expressions import Subquery
from tortoise.functions import Max
from tortoise.queryset import QuerySetSingle, QuerySet

from piltover.db import models
from piltover.db.enums import PeerType
from piltover.exceptions import Unreachable
from piltover.tl.types import SavedDialog as TLSavedDialog


class SavedDialog(Model):
    id: int = fields.BigIntField(pk=True)
    pinned_index: int | None = fields.SmallIntField(null=True, default=None)
    peer: models.Peer = fields.OneToOneField("models.Peer")

    peer_id: int

    def top_message_query(self, prefetch: bool = True) -> QuerySetSingle[models.MessageRef]:
        query = models.MessageRef.filter(
            peer__owner=self.peer.owner, peer__type=PeerType.SELF, content__fwd_header__saved_peer=self.peer,
        ).order_by("-id").first()
        if prefetch:
            return query.select_related(*models.MessageRef.PREFETCH_FIELDS)
        return query

    @classmethod
    def top_message_query_bulk(
            cls, user: models.User, dialogs: list[SavedDialog], prefetch: bool = True
    ) -> QuerySet[models.MessageRef]:
        peer_ids = [dialog.peer_id for dialog in dialogs]
        return models.MessageRef.filter(
            id__in=Subquery(
                models.MessageRef.filter(
                    peer__owner=user, peer__type=PeerType.SELF, content__fwd_header__saved_peer__id__in=peer_ids,
                ).group_by("content__fwd_header__saved_peer__id").annotate(max_id=Max("id")).values("max_id")
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

    async def to_tl(self) -> TLSavedDialog:
        top_message_id = await self.top_message_query(False).values_list("id", flat=True)
        top_message_id = top_message_id or 0

        return TLSavedDialog(
            pinned=False,
            peer=self.peer.to_tl(),
            top_message=top_message_id,
        )

    @classmethod
    async def to_tl_bulk(
            cls, dialogs: list[SavedDialog],
            messages: dict[tuple[PeerType, int], tuple[SavedDialog, models.MessageRef | None]],
    ) -> list[TLSavedDialog]:
        tl = []
        for dialog in dialogs:
            top_message = 0
            peer_key = dialog.peer_key()
            if peer_key in messages and messages[peer_key][1] is not None:
                top_message = messages[peer_key][1].id

            tl.append(TLSavedDialog(
                pinned=False,
                peer=dialog.peer.to_tl(),
                top_message=top_message,
            ))

        return tl
