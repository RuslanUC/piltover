from __future__ import annotations
from tortoise import fields, Model
from tortoise.fields import OneToOneNullableRelation

from piltover.db import models


def NullableOneToOne(to: str, related_name: str) -> OneToOneNullableRelation:
    return fields.OneToOneField(to, null=True, default=None, related_name=related_name)


class Username(Model):
    id: int = fields.BigIntField(primary_key=True)
    username: str = fields.CharField(max_length=64, unique=True)
    user: models.User | None = NullableOneToOne("models.User", related_name="username")
    channel: models.Channel | None = NullableOneToOne("models.Channel", related_name="username")

    user_id: int | None
    channel_id: int | None
