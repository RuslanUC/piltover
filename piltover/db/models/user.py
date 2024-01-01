from __future__ import annotations
from tortoise import fields

from piltover.db import models
from piltover.tl_new.types.user import User as TLUser
from piltover.db.models._utils import Model


class User(Model):
    id: int = fields.BigIntField(pk=True)
    phone_number: str = fields.CharField(unique=True, max_length=20)
    first_name: str = fields.CharField(max_length=128)
    last_name: str | None = fields.CharField(max_length=128, null=True, default=None)
    username: str | None = fields.CharField(max_length=64, null=True, default=None, index=True)
    lang_code: str = fields.CharField(max_length=8, default="en")
    about: str | None = fields.CharField(max_length=240, null=True, default=None)

    def to_tl(self, current_user: models.User | None = None, **kwargs) -> TLUser:
        defaults = {
            "contact": False,
            "mutual_contact": False,
            "deleted": False,
            "bot": False,
            "verified": True,
            "restricted": False,
            "min": False,
            "support": False,
            "scam": False,
            "apply_min_photo": False,
            "fake": False,
            "bot_attach_menu": False,
            "premium": False,
            "attach_menu_enabled": False,
            "access_hash": 0,
        } | kwargs

        return TLUser(
            **defaults,
            id=self.id,
            first_name=self.first_name,
            last_name=self.last_name,
            username=self.username,
            phone=self.phone_number,
            lang_code=self.lang_code,
            is_self=self == current_user,
        )
