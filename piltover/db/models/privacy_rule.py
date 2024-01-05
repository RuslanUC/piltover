from __future__ import annotations

from datetime import datetime
from time import mktime

from tortoise import fields

from piltover.db import models
from piltover.db.enums import PrivacyRuleKeyType
from piltover.db.models._utils import Model
from piltover.tl_new.types import Message as TLMessage


class PrivacyRule(Model):
    id: int = fields.BigIntField(pk=True)
    user: models.User = fields.ForeignKeyField("models.User", on_delete=fields.CASCADE)
    key: PrivacyRuleKeyType = fields.IntEnumField(PrivacyRuleKeyType)
    # value: what?
