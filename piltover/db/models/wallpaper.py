from __future__ import annotations

import hashlib
import hmac
from typing import Self

from tortoise import Model, fields
from tortoise.expressions import Q

from piltover.app_config import AppConfig
from piltover.db import models
from piltover.exceptions import Unreachable
from piltover.tl import Long, base
from piltover.tl.to_format import WallPaperToFormat
from piltover.tl.types import WallPaper, WallPaperNoFile, InputWallPaper, InputWallPaperSlug, InputWallPaperNoFile
from piltover.tl.types.internal_access import AccessHashPayloadWallpaper


class Wallpaper(Model):
    id: int = fields.BigIntField(pk=True)
    creator: models.User | None = fields.ForeignKeyField("models.User", null=True)
    slug: str = fields.CharField(max_length=64, unique=True)
    pattern: bool = fields.BooleanField()
    dark: bool = fields.BooleanField()
    document: models.File | None = fields.ForeignKeyField("models.File", null=True)
    settings: models.WallpaperSettings | None = fields.ForeignKeyField("models.WallpaperSettings", null=True)

    creator_id: int
    document_id: int | None
    settings_id: int | None

    def to_tl(
            self, settings: models.WallpaperSettings | None = None,
    ) -> WallPaper | WallPaperNoFile | WallPaperToFormat:
        if settings is None:
            settings = self.settings

        if self.document is None:
            return WallPaperNoFile(
                id=self.id,
                default=False,
                dark=self.dark,
                settings=settings.to_tl() if settings is not None else None,
            )

        return WallPaperToFormat(
            id=self.id,
            creator_id=self.creator_id or 0,
            pattern=self.pattern,
            dark=self.dark,
            slug=self.slug,
            document=self.document.to_tl_document(),
            settings=settings.to_tl() if settings is not None else None,
        )

    @classmethod
    async def from_input(
            cls, wp: base.InputWallPaper, user: models.User | None = None, auth_id: int | None = None,
    ) -> Self | None:
        q = cls.from_input_q(wp, user, auth_id)
        if q is None:
            return None
        return await Wallpaper.get_or_none(q).select_related("document", "settings")

    @classmethod
    def from_input_q(
            cls, wp: base.InputWallPaper, user: models.User | None = None, auth_id: int | None = None,
    ) -> Q | None:
        if isinstance(wp, InputWallPaper):
            if user is None:
                return None
            if not cls.check_access_hash(user.id, auth_id, wp.id, wp.access_hash):
                return None
            return Q(id=wp.id)
        elif isinstance(wp, InputWallPaperNoFile):
            return Q(id=wp.id, document=None)
        elif isinstance(wp, InputWallPaperSlug):
            return Q(slug=wp.slug)
        else:
            raise Unreachable

    @staticmethod
    def make_access_hash(user: int, auth: int, wallpaper: int) -> int:
        to_sign = AccessHashPayloadWallpaper(this_user_id=user, wallpaper_id=wallpaper, auth_id=auth).write()
        digest = hmac.new(AppConfig.HMAC_KEY, to_sign, hashlib.sha256).digest()
        return Long.read_bytes(digest[-8:])

    @staticmethod
    def check_access_hash(user: int, auth: int, wallpaper: int, access_hash: int) -> bool:
        return Wallpaper.make_access_hash(user, auth, wallpaper) == access_hash
