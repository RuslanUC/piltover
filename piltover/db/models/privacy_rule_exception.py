from __future__ import annotations

from tortoise import fields, Model

from piltover.db import models


class PrivacyRuleException(Model):
    id: int = fields.BigIntField(pk=True)
    rule: models.PrivacyRule = fields.ForeignKeyField("models.PrivacyRule", related_name="exceptions")
    # TODO: make nullable when chat/channel exceptions will be added
    user: models.User = fields.ForeignKeyField("models.User")
    allow: bool = fields.BooleanField()

    user_id: int

    class Meta:
        unique_together = (
            ("rule", "user"),
        )
