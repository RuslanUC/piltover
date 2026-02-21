from __future__ import annotations

from tortoise import fields, Model
from tortoise.expressions import Q, Subquery
from tortoise.functions import Coalesce

from piltover.db import models
from piltover.db.enums import PeerType
from piltover.exceptions import Unreachable


class DiscussionReadState(Model):
    id: int = fields.BigIntField(pk=True)
    user: models.User = fields.ForeignKeyField("models.User")
    # TODO: use fk field with OnDelete.NO_ACTION
    discussion_message_id: int = fields.BigIntField()
    last_message_id: int = fields.BigIntField(default=0)

    user_id: int

    class Meta:
        unique_together = (
            ("user", "discussion_message_id"),
        )
