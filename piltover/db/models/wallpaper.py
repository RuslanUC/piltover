from __future__ import annotations

import hmac
from hashlib import sha256
from typing import Self

from tortoise import Model, fields

from piltover.app_config import AppConfig
from piltover.context import request_ctx
from piltover.db import models
from piltover.exceptions import Unreachable
from piltover.tl import Long, base
from piltover.tl.types import WallPaper, WallPaperNoFile, InputWallPaper, InputWallPaperSlug, InputWallPaperNoFile


class Wallpaper(Model):
    id: int = fields.BigIntField(pk=True)
    creator: models.User | None = fields.ForeignKeyField("models.User", null=True)
    slug: str = fields.CharField(max_length=64, unique=True)
    pattern: bool = fields.BooleanField()
    dark: bool = fields.BooleanField()
    document: models.File | None = fields.ForeignKeyField("models.File", null=True)

    creator_id: int
    document_id: int | None

    @classmethod
    def make_access_hash(cls, wallpaper_id: int, user: models.User, auth_id: int | None = None) -> int:
        if auth_id is None:
            auth_id = request_ctx.get().auth_id

        payload = Long.write(WallPaper.tlid()) + Long.write(wallpaper_id) + Long.write(user.id) + Long.write(auth_id)
        hmac_digest = hmac.new(AppConfig.HMAC_KEY, payload, sha256).digest()
        return Long.read_bytes(hmac_digest[:8])

    async def to_tl(self, user: models.User) -> WallPaper | WallPaperNoFile:
        settings = await models.WallpaperSettings.get_or_none(wallpaper=self)

        if self.document is None:
            return WallPaperNoFile(
                id=self.id,
                default=False,
                dark=self.dark,
                settings=settings.to_tl() if settings is not None else None,
            )

        return WallPaper(
            id=self.id,
            creator=self.creator_id == user.id,
            default=False,
            pattern=self.pattern,
            dark=self.dark,
            access_hash=self.make_access_hash(self.id, user),
            slug=self.slug,
            document=await self.document.to_tl_document(user),
            settings=settings.to_tl() if settings is not None else None,
        )

    @classmethod
    async def from_input(
            cls, wp: base.InputWallPaper, user: models.User | None = None, auth_id: int | None = None,
    ) -> Self | None:
        if isinstance(wp, InputWallPaper):
            if user is None:
                return None
            if cls.make_access_hash(wp.id, user, auth_id) != wp.access_hash:
                return None
            return await Wallpaper.get_or_none(id=wp.id).select_related("document")
        elif isinstance(wp, InputWallPaperNoFile):
            return await Wallpaper.get_or_none(id=wp.id, document=None)
        elif isinstance(wp, InputWallPaperSlug):
            return await Wallpaper.get_or_none(slug=wp.slug).select_related("document")
        else:
            raise Unreachable
