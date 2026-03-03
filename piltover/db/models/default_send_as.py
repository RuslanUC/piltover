from tortoise import Model, fields

from piltover.db import models


class DefaultSendAs(Model):
    id: int = fields.BigIntField(pk=True)
    user: models.User = fields.ForeignKeyField("models.User")
    group: models.Channel = fields.ForeignKeyField("models.Channel", related_name="default_send_as_group")
    channel: models.Channel = fields.ForeignKeyField("models.Channel", related_name="default_send_as_channel")

    user_id: int
    group_id: int
    channel_id: int

    class Meta:
        unique_together = (
            ("user_id", "group_id",),
        )
