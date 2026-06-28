from __future__ import annotations

from tortoise import Model, fields

from piltover.db import models


class TelegramUser(Model):
    id: int = fields.BigIntField(primary_key=True)
    user: models.User = fields.OneToOneField("models.User")
    telegram_id: int = fields.BigIntField(db_index=True)
