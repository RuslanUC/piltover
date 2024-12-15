from __future__ import annotations

from datetime import datetime
from time import time

from tortoise import fields

from piltover.db import models
from piltover.db.enums import UpdateType
from piltover.db.models._utils import Model


def gen_date() -> int:
    return int(time())


# TODO: delete
class Update(Model):
    id: int = fields.BigIntField(pk=True)
    pts: int = fields.BigIntField()
    date: int = fields.BigIntField(default=gen_date)
    update_type: int = fields.BigIntField()
    update_data: bytes = fields.BinaryField()
    user_ids_to_fetch: list[int] = fields.JSONField(null=True, default=None)
    user: models.User = fields.ForeignKeyField("models.User", on_delete=fields.CASCADE)


class UpdateV2(Model):
    id: int = fields.BigIntField(pk=True)
    update_type: UpdateType = fields.IntEnumField(UpdateType)
    pts: int = fields.BigIntField()
    date: datetime = fields.DatetimeField(auto_now_add=True)
    related_id: int = fields.BigIntField(index=True, null=True)
    # TODO: probably there is a better way to store multiple updates (right now it is only used for deleted messages,
    #  so maybe create two tables: something like UpdateDeletedMessage and UpdateDeletedMessageId, related_id will point to
    #  UpdateDeletedMessage.id and UpdateDeletedMessage will have one-to-many relation to UpdateDeletedMessageId)
    related_ids: list[int] = fields.JSONField(null=True, default=None)
    user: models.User = fields.ForeignKeyField("models.User")
    # TODO?: for supergroups/channels
    #parent_chat: models.Chat = fields.ForeignKeyField("models.Chat", null=True, default=None)
