from __future__ import annotations

import hmac
from hashlib import sha256

from tortoise import Model, fields

from piltover.app_config import AppConfig
from piltover.context import request_ctx
from piltover.db import models
from piltover.tl import Long
from piltover.tl.types import Theme as TLTheme


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

    def make_access_hash(self, user: models.User, auth_id: int | None = None) -> int:
        if auth_id is None:
            auth_id = request_ctx.get().auth_id

        payload = Long.write(TLTheme.tlid()) + Long.write(self.id) + Long.write(user.id) + Long.write(auth_id)
        hmac_digest = hmac.new(AppConfig.HMAC_KEY, payload, sha256).digest()
        return Long.read_bytes(hmac_digest[:8])

    async def to_tl(self, user: models.User) -> TLTheme:
        return TLTheme(
            creator=self.creator_id == user.id,
            default=False,
            for_chat=self.for_chat,
            id=self.id,
            access_hash=self.make_access_hash(user),
            slug=self.slug,
            title=self.title,
            document=await self.document.to_tl_document(user) if self.document is not None else None,
            settings=[
                await settings.to_tl(user)
                for settings in await models.ThemeSettings.filter(theme=self).select_related(
                    "wallpaper", "wallpaper__document", "wallpaper__settings",
                )
            ],
            emoticon=self.emoticon,
            installs_count=None,  # TODO: count installs maybe
        )

