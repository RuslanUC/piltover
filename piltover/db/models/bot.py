from __future__ import annotations

from base64 import urlsafe_b64encode

from fastrand import xorshift128plus_bytes
from tortoise import Model, fields

from piltover.db import models


def gen_bot_token() -> str:
    rand_bytes = xorshift128plus_bytes(24)
    return urlsafe_b64encode(rand_bytes).decode("utf8")


class Bot(Model):
    id: int = fields.BigIntField(pk=True)
    owner: models.User = fields.ForeignKeyField("models.User", related_name="bot_owner")
    bot: models.User = fields.OneToOneField("models.User", related_name="bot_bot")
    token_nonce: str = fields.CharField(max_length=36, default=gen_bot_token)
