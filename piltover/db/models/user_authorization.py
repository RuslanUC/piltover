from __future__ import annotations

from datetime import datetime
from os import urandom
from time import mktime

from tortoise import fields

from piltover.db import models
from piltover.db.models._utils import Model
from piltover.tl_new import Authorization


def gen_hash():
    return urandom(16).hex()


class UserAuthorization(Model):
    id: int = fields.BigIntField(pk=True)
    hash: str = fields.CharField(max_length=32, index=True, default=gen_hash)
    ip: str = fields.CharField(max_length=64)
    created_at: datetime = fields.DatetimeField(default=datetime.now)
    active_at: datetime = fields.DatetimeField(default=datetime.now)

    platform: str = fields.CharField(max_length=128, default="Unknown")
    device_model: str = fields.CharField(max_length=128, default="Unknown")
    system_version: str = fields.CharField(max_length=32, default="Unknown")
    app_version: str = fields.CharField(max_length=32, default="Unknown")

    #app: models.ApiApplication = fields.ForeignKeyField("models.ApiApplication")
    user: models.User = fields.ForeignKeyField("models.User", on_delete=fields.CASCADE)
    key: models.AuthKey = fields.ForeignKeyField("models.AuthKey", on_delete=fields.CASCADE, unique=True)

    def to_tl(self, **kwargs) -> Authorization:
        kwargs["hash"] = 0 if kwargs.get("current", False) else int(self.hash[:-16], 16)
        defaults = {
            "official_app": True,
            "encrypted_requests_disabled": True,
            "call_requests_disabled": True,
            "country": "US",
            "region": "Telegram HQ",
        } | kwargs

        return Authorization(
            api_id=1,
            app_name="Test",
            date_created=int(mktime(self.created_at.timetuple())),
            date_active=int(mktime(self.active_at.timetuple())),
            ip=self.ip,
            platform=self.platform,
            device_model=self.device_model,
            system_version=self.system_version,
            app_version=self.app_version,
            **defaults
        )
