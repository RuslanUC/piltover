from tortoise import fields, Model

from piltover.db import models


class MessageComments(Model):
    id: int = fields.BigIntField(pk=True)
    discussion_channel: models.Channel = fields.ForeignKeyField("models.Channel")
    discussion_pts: int = fields.BigIntField()

    discussion_channel_id: int

