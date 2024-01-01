from __future__ import annotations

from datetime import datetime
from time import mktime

from tortoise import fields

from piltover.db import models
from piltover.db.models._utils import Model
from piltover.tl_new.types import Message as TLMessage


class Message(Model):
    id: int = fields.BigIntField(pk=True)
    message: str = fields.TextField()
    pinned: bool = fields.BooleanField(default=False)
    date: datetime = fields.DatetimeField(default=datetime.now)

    author: models.User = fields.ForeignKeyField("models.User", on_delete=fields.SET_NULL, null=True)
    chat: models.Chat = fields.ForeignKeyField("models.Chat", on_delete=fields.CASCADE)

    #reply_to: models.Message = fields.ForeignKeyField("models.Message", null=True, default=None, on_delete=fields.SET_NULL)  # ??

    async def to_tl(self, current_user: models.User, **kwargs) -> TLMessage:
        defaults = {
            "mentioned": False,
            "media_unread": False,
            "silent": False,
            "post": False,
            "from_scheduled": False,
            "legacy": False,
            "edit_hide": False,
            "noforwards": False,
            "entities": [],
            "restriction_reason": []
        }

        return TLMessage(
            id=self.id,
            message=self.message,
            pinned=self.pinned,
            peer_id=await self.chat.get_peer(current_user),
            date=int(mktime(self.date.timetuple())),
            out=current_user == self.author,
            **defaults
        )
