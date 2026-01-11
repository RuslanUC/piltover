from __future__ import annotations

from datetime import datetime

from tortoise import fields, Model

from piltover.db import models
from piltover.tl import MessageFwdHeader as TLMessageFwdHeader, PeerUser, PeerChat, PeerChannel


class MessageFwdHeader(Model):
    id: int = fields.BigIntField(pk=True)
    from_user: models.User = fields.ForeignKeyField("models.User", null=True, default=None, related_name="from_user")
    from_chat: models.Chat = fields.ForeignKeyField("models.Chat", null=True, default=None, related_name="from_chat")
    from_channel: models.Channel = fields.ForeignKeyField("models.Channel", null=True, default=None, related_name="from_channel")
    from_name: str = fields.CharField(max_length=64)
    date: datetime = fields.DatetimeField()
    saved_out: bool = fields.BooleanField()

    channel_post_id: int | None = fields.BigIntField(null=True, default=None)
    channel_post_author: str | None = fields.CharField(max_length=128, null=True, default=None)

    saved_peer: models.Peer = fields.ForeignKeyField("models.Peer", null=True, default=None, related_name="saved_peer")
    saved_id: int = fields.BigIntField(null=True, default=None)
    # TODO: saved_from can also be channel or chat
    saved_from: models.User = fields.ForeignKeyField("models.User", null=True, default=None, related_name="saved_user")
    saved_name: str = fields.CharField(max_length=64, null=True, default=None)
    saved_date: datetime = fields.DatetimeField(null=True, default=None)

    from_user_id: int | None
    from_chat_id: int | None
    from_channel_id: int | None
    saved_peer_id: int | None
    saved_from_id: int | None

    def to_tl(self) -> TLMessageFwdHeader:
        from_id = None
        if self.from_user_id is not None:
            from_id = PeerUser(user_id=self.from_user_id)
        elif self.from_chat_id is not None:
            from_id = PeerChat(chat_id=models.Chat.make_id_from(self.from_chat_id))
        elif self.from_channel_id is not None:
            from_id = PeerChannel(channel_id=models.Channel.make_id_from(self.from_channel_id))

        return TLMessageFwdHeader(
            saved_out=self.saved_out,
            from_id=from_id,
            from_name=self.from_name,
            date=int(self.date.timestamp()),
            channel_post=self.channel_post_id,
            post_author=self.channel_post_author,
            saved_from_peer=self.saved_peer.to_tl() if self.saved_peer is not None else None,
            saved_from_msg_id=self.saved_id,
            saved_from_id=PeerUser(user_id=self.saved_from_id) if self.saved_from_id else None,
            saved_from_name=self.saved_name,
            saved_date=int(self.saved_date.timestamp()) if self.saved_date else None,
        )
