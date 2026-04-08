from __future__ import annotations

from tortoise import fields, Model

from piltover.db import models


class DiscussionReadState(Model):
    id: int = fields.BigIntField(primary_key=True)
    user: models.User = fields.ForeignKeyField("models.User")
    # TODO: use fk field with OnDelete.NO_ACTION
    discussion_message_id: int = fields.BigIntField()
    last_message_id: int = fields.BigIntField(default=0)

    user_id: int

    class Meta:
        unique_together = (
            ("user", "discussion_message_id"),
        )
