from datetime import datetime

from tortoise import Model, fields

from piltover.db import models


class WebpageMetadata(Model):
    id: int = fields.BigIntField(primary_key=True)
    url: str = fields.CharField(max_length=512)
    created_at: datetime = fields.DateTimeField(auto_now_add=True)
    pending: bool = fields.BooleanField(default=True)
    title: str | None = fields.CharField(max_length=128, null=True, default=None)
    site_name: str | None = fields.CharField(max_length=64, null=True, default=None)
    description: str | None = fields.CharField(max_length=512, null=True, default=None)
    image: models.File = fields.ForeignKeyField("models.File", null=True, default=None)

    class Meta:
        indexes = (
            ("url", "created_at"),
        )
