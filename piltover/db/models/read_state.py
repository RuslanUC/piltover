from __future__ import annotations

from tortoise import fields, Model

from piltover.db import models
from piltover.db.enums import PeerType


class ReadState(Model):
    id: int = fields.BigIntField(pk=True)
    last_message_id: int = fields.BigIntField()
    peer: models.Peer = fields.ForeignKeyField("models.Peer", on_delete=fields.CASCADE, unique=True)

    @classmethod
    async def get_in_out_ids_and_unread(cls, peer: models.Peer) -> tuple[int, int, int]:
        in_read_state, _ = await models.ReadState.get_or_create(peer=peer, defaults={"last_message_id": 0})
        unread_count = await models.Message.filter(peer=peer, id__gt=in_read_state.last_message_id).count()

        out_read_max_id = 0
        if peer.type is PeerType.SELF:
            out_read_max_id = in_read_state.last_message_id
        elif peer.type is PeerType.USER:
            out_read_max_id = await models.ReadState.filter(
                peer__owner__id=peer.user_id, peer__user__id=peer.owner_id
            ).first().values_list("last_message_id", flat=True) or 0
        elif peer.type is PeerType.CHAT:
            out_read_state = await models.ReadState.filter(
                peer__chat__id=peer.chat_id, peer__id__not=peer.id
            ).order_by("-last_message_id").first()
            if out_read_state:
                out_read_max_id = await models.Message.filter(
                    peer=peer, id__lte=out_read_state.last_message_id
                ).order_by("-id").first().values_list("id", flat=True)
                out_read_max_id = out_read_max_id or 0
        elif peer.type is PeerType.CHANNEL:
            out_read_max_id = 0
            # TODO: if supergroup, do same as in case with PeerType.CHAT
            # out_read_state = await models.ReadState.filter(
            #     peer__channel__id=self.peer.channel_id, peer__id__not=self.peer.id
            # ).order_by("-last_message_id").first()
            # if out_read_state:
            #     out_read_max_id = await models.Message.filter(
            #         peer=self.peer, id__lte=out_read_state.last_message_id
            #     ).order_by("-id").first().values_list("id", flat=True)
            #     out_read_max_id = out_read_max_id or 0

        return in_read_state.last_message_id, out_read_max_id or 0, unread_count

