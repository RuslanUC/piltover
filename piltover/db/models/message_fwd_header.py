from __future__ import annotations

from datetime import datetime

from tortoise import fields, Model

from piltover.db import models
from piltover.tl import MessageFwdHeader as TLMessageFwdHeader, PeerUser


class MessageFwdHeader(Model):
    id: int = fields.BigIntField(pk=True)
    # TODO: add from_channel
    from_user: models.User = fields.ForeignKeyField("models.User", null=True, default=None, related_name="from_user")
    from_name: str = fields.CharField(max_length=64)
    date: datetime = fields.DatetimeField()

    saved_peer: models.Peer = fields.ForeignKeyField("models.Peer", null=True, default=None, related_name="saved_peer")
    saved_id: int = fields.BigIntField(null=True, default=None)
    saved_from: models.User = fields.ForeignKeyField("models.User", null=True, default=None, related_name="saved_user")
    saved_name: str = fields.CharField(max_length=64, null=True, default=None)
    saved_date: datetime = fields.DatetimeField(null=True, default=None)

    from_user_id: int
    saved_peer_id: int
    saved_from_id: int

    async def to_tl(self) -> TLMessageFwdHeader:
        if self.saved_peer is not None:
            self.saved_peer = await self.saved_peer

        return TLMessageFwdHeader(
            from_id=PeerUser(user_id=self.from_user_id) if self.from_user_id else None,
            from_name=self.from_name,
            date=int(self.date.timestamp()),
            saved_from_peer=self.saved_peer.to_tl() if self.saved_peer is not None else None,
            saved_from_msg_id=self.saved_id,
            saved_from_id=PeerUser(user_id=self.saved_from_id) if self.saved_from_id else None,
            saved_from_name=self.saved_name,
            saved_date=int(self.saved_date.timestamp()) if self.saved_date else None,
        )
