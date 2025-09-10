from __future__ import annotations

from datetime import datetime

from tortoise import fields, Model

from piltover.db import models


class UserPasswordReset(Model):
    id: int = fields.BigIntField(pk=True)
    user: models.User = fields.OneToOneField("models.User")
    date: datetime = fields.DatetimeField(auto_now_add=True)
