from __future__ import annotations

from datetime import datetime

from tortoise import Model, fields

from piltover.db import models


class ChatInviteRequest(Model):
    id: int = fields.BigIntField(pk=True)
    user: models.User = fields.ForeignKeyField("models.User")
    invite: models.ChatInvite = fields.ForeignKeyField("models.ChatInvite")
    created_at: datetime = fields.DatetimeField(auto_now_add=True)

    user_id: int | None
    invite_id: int | None
