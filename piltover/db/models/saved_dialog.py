from __future__ import annotations

from typing import cast

from tortoise.expressions import Subquery
from tortoise.functions import Max
from tortoise.queryset import QuerySet

from piltover.db import models
from piltover.db.enums import PeerType
from piltover.db.models.dialog_base import DialogBase
from piltover.exceptions import Unreachable
from piltover.tl.types import SavedDialog as TLSavedDialog


class SavedDialog(DialogBase):
    class Meta:
        unique_together = (
            ("owner_id", "peer_id"),
        )

    @classmethod
    def top_message_query_bulk(
            cls, user_id: int, dialogs: list[SavedDialog], prefetch: bool = True
    ) -> QuerySet[models.MessageRef]:
        peer_ids = [dialog.peer_id for dialog in dialogs]
        return models.MessageRef.filter(
            id__in=Subquery(
                models.MessageRef.filter(
                    peer__owner_id=user_id, peer__user_id=user_id,
                    content__fwd_header__saved_peer_id__in=peer_ids,
                ).group_by("content__fwd_header__saved_peer_id").annotate(max_id=Max("id")).values("max_id")
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
        top_message_id = cast(
            int | None,
            cast(
                object,
                await models.MessageRef.filter(
                    peer__owner_id=self.owner_id, peer__user_id=self.owner_id,
                    content__fwd_header__saved_peer=self.peer,
                ).order_by("-id").first().values_list("id", flat=True)
            )
        )

        return TLSavedDialog(
            pinned=False,
            peer=self.peer.to_tl(),
            top_message=top_message_id or 0,
        )

    @classmethod
    async def to_tl_bulk(
            cls, dialogs: list[SavedDialog],
            messages: dict[int, tuple[SavedDialog, models.MessageRef | None]],
    ) -> list[TLSavedDialog]:
        tl = []
        for dialog in dialogs:
            top_message = 0
            peer_id = dialog.peer_id
            if peer_id in messages and (peer_message := messages[peer_id][1]) is not None:
                top_message = peer_message.id

            tl.append(TLSavedDialog(
                pinned=False,
                peer=dialog.peer.to_tl(),
                top_message=top_message,
            ))

        return tl
