from datetime import datetime

from tortoise import fields, Model

from piltover.db import models


class SavedGif(Model):
    id: int = fields.BigIntField(pk=True)
    user: models.User = fields.ForeignKeyField("models.User")
    gif: models.File = fields.ForeignKeyField("models.File")
    last_access: datetime = fields.DatetimeField(auto_now_add=True)

    user_id: int
    gif_id: int
