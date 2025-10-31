from __future__ import annotations

from tortoise import Model, fields

from piltover.db import models


class UserPersonalChannel(Model):
    id: int = fields.BigIntField(pk=True)
    user: models.User = fields.OneToOneField("models.User")
    channel: models.Channel = fields.OneToOneField("models.Channel")
