from __future__ import annotations

from tortoise import fields, Model


class MessageLink(Model):
    id: int = fields.BigIntField(primary_key=True)
