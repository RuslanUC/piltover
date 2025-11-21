from __future__ import annotations

import hashlib
import hmac

from tortoise import Model, fields

from piltover.app_config import AppConfig
from piltover.db import models
from piltover.tl import Long
from piltover.tl.types import Theme as TLTheme
from piltover.tl.types.internal_access import AccessHashPayloadTheme


class Theme(Model):
    id: int = fields.BigIntField(pk=True)
    creator: models.User | None = fields.ForeignKeyField("models.User", null=True)
    title: str = fields.CharField(max_length=128)
    slug: str = fields.CharField(max_length=64, unique=True)
    for_chat: bool = fields.BooleanField(default=False)
    emoticon: str | None = fields.CharField(max_length=8, null=True, default=None)
    document: models.File | None = fields.ForeignKeyField("models.File", null=True)

    creator_id: int
    document_id: int | None

    async def to_tl(self, user: models.User) -> TLTheme:
        return TLTheme(
            creator=self.creator_id == user.id,
            default=False,
            for_chat=self.for_chat,
            id=self.id,
            access_hash=-1,
            slug=self.slug,
            title=self.title,
            document=await self.document.to_tl_document() if self.document is not None else None,
            settings=[
                await settings.to_tl(user)
                for settings in await models.ThemeSettings.filter(theme=self).select_related(
                    "wallpaper", "wallpaper__document", "wallpaper__settings",
                )
            ],
            emoticon=self.emoticon,
            installs_count=None,  # TODO: count installs maybe
        )

    @staticmethod
    def make_access_hash(user: int, auth: int, theme: int) -> int:
        to_sign = AccessHashPayloadTheme(this_user_id=user, theme_id=theme, auth_id=auth).write()
        digest = hmac.new(AppConfig.HMAC_KEY, to_sign, hashlib.sha256).digest()
        return Long.read_bytes(digest[-8:])

    @staticmethod
    def check_access_hash(user: int, auth: int, theme: int, access_hash: int) -> bool:
        return Theme.make_access_hash(user, auth, theme) == access_hash

