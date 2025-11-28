from __future__ import annotations

from os import urandom
from typing import Generator

from tortoise import Model, fields
from tortoise.expressions import Q
from tortoise.queryset import QuerySet

from piltover.db import models
from piltover.db.enums import StickerSetType
from piltover.tl import StickerSet, InputStickerSetEmpty, InputStickerSetID, InputStickerSetShortName, Long, PhotoSize
from piltover.tl.types.messages import StickerSet as MessagesStickerSet


class Stickerset(Model):
    id: int = fields.BigIntField(pk=True)
    title: str = fields.CharField(max_length=64)
    short_name: str | None = fields.CharField(max_length=64, unique=True, null=True)
    access_hash: int = fields.BigIntField(default=lambda: Long.read_bytes(urandom(8)))
    owner: models.User | None = fields.ForeignKeyField("models.User", null=True)
    official: bool = fields.BooleanField(default=False)
    hash: int = fields.IntField(default=0)
    type: StickerSetType = fields.IntEnumField(StickerSetType)
    deleted: bool = fields.BooleanField(default=False)

    owner_id: int | None

    @staticmethod
    def from_input_q(
            input_set: InputStickerSetEmpty | InputStickerSetID | InputStickerSetShortName | None,
            prefix: str | None = None,
    ) -> Q | None:
        prefix = f"{prefix}__" if prefix is not None else ""
        if input_set is None or isinstance(input_set, InputStickerSetEmpty):
            return None
        elif isinstance(input_set, InputStickerSetID):
            return Q(**{
                f"{prefix}id": input_set.id, f"{prefix}access_hash": input_set.access_hash, "deleted": False,
            })
        elif isinstance(input_set, InputStickerSetShortName):
            return Q(**{f"{prefix}short_name": input_set.short_name, "deleted": False})

        # TODO: support InputStickerSetAnimatedEmoji
        # TODO: support InputStickerSetDice
        # TODO: support InputStickerSetAnimatedEmojiAnimations
        # TODO: support InputStickerSetPremiumGifts
        # TODO: support InputStickerSetEmojiGenericAnimations
        # TODO: support InputStickerSetEmojiDefaultStatuses
        # TODO: support InputStickerSetEmojiDefaultTopicIcons
        # TODO: support InputStickerSetEmojiChannelDefaultStatuses

        return None

    @classmethod
    async def from_input(
            cls, input_set: InputStickerSetEmpty | InputStickerSetID | InputStickerSetShortName | None
    ) -> Stickerset | None:
        if (q := cls.from_input_q(input_set)) is None:
            return None
        return await cls.get_or_none(q)

    async def to_tl(self, user: models.User) -> StickerSet:
        installed = await models.InstalledStickerset.get_or_none(set=self, user=user)
        thumb = await models.StickersetThumb.filter(set=self).select_related("file").order_by("-id").first()

        return StickerSet(
            id=self.id,
            access_hash=self.access_hash,
            title=self.title,
            short_name=self.short_name,
            official=self.official,
            creator=user.id == self.owner_id,
            installed_date=int(installed.installed_at.timestamp()) if installed is not None else None,
            archived=installed is not None and installed.archived,
            count=await self.documents_query().count(),
            hash=self.hash,
            masks=self.type is StickerSetType.MASKS,
            emojis=self.type is StickerSetType.EMOJIS,

            thumbs=[PhotoSize(type_="s", w=100, h=100, size=thumb.file.size)] if thumb is not None else None,
            thumb_dc_id=2 if thumb is not None else None,
            thumb_version=thumb.id if thumb is not None else None,
            thumb_document_id=None,

            text_color=False,
            channel_emoji_status=False,
        )

    def documents_query(self) -> QuerySet[models.File]:
        return models.File.filter(stickerset=self).order_by("sticker_pos").select_related("stickerset")

    def gen_for_hash(self, stickers: list[models.File]) -> Generator[str | int, None, None]:
        yield self.id
        yield self.title

        for sticker in stickers:
            yield sticker.id
            yield sticker.sticker_pos
            yield sticker.sticker_alt

    async def to_tl_messages(self, user: models.User) -> MessagesStickerSet:
        return MessagesStickerSet(
            set=await self.to_tl(user),
            packs=[],
            keywords=[],  # TODO: add support for keywords
            documents=[
                file.to_tl_document()
                for file in await self.documents_query()
            ],
        )
