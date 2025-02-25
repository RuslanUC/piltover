from __future__ import annotations

from datetime import datetime
from os import urandom

from tortoise import fields, Model

from piltover.db import models
from piltover.tl import Authorization


def gen_hash():
    return urandom(16).hex()


class UserAuthorization(Model):
    id: int = fields.BigIntField(pk=True)
    hash: str = fields.CharField(max_length=32, index=True, default=gen_hash)
    ip: str = fields.CharField(max_length=64)
    created_at: datetime = fields.DatetimeField(default=datetime.now)
    active_at: datetime = fields.DatetimeField(default=datetime.now)
    mfa_pending: bool = fields.BooleanField(default=False)

    platform: str = fields.CharField(max_length=128, default="Unknown")
    device_model: str = fields.CharField(max_length=128, default="Unknown")
    system_version: str = fields.CharField(max_length=32, default="Unknown")
    app_version: str = fields.CharField(max_length=32, default="Unknown")

    upd_seq: int = fields.BigIntField(default=0)

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
            date_created=int(self.created_at.timestamp()),
            date_active=int(self.active_at.timestamp()),
            ip=self.ip,
            platform=self.platform,
            device_model=self.device_model,
            system_version=self.system_version,
            app_version=self.app_version,
            password_pending=self.mfa_pending,
            **defaults
        )
