from tortoise import fields, Model

from piltover.db import models


class Contact(Model):
    id: int = fields.BigIntField(pk=True)
    owner: models.User = fields.ForeignKeyField("models.User", related_name="contact_owner")
    target: models.User | None = fields.ForeignKeyField("models.User", related_name="target", null=True, default=None)
    phone_number: str | None = fields.CharField(unique=True, max_length=20, null=True, default=None)
    first_name: str = fields.CharField(max_length=128, null=True, default=None)
    last_name: str = fields.CharField(max_length=128, null=True, default=None)

    target_id: int

    class Meta:
        unique_together = (
            ("owner", "target"),
            ("owner", "phone_number"),
        )

