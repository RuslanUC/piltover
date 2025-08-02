from __future__ import annotations

from os import urandom
from typing import Generator

from tortoise import Model, fields
from tortoise.queryset import QuerySet

from piltover.db import models
from piltover.tl import StickerSet, InputStickerSetEmpty, InputStickerSetID, InputStickerSetShortName, Long
from piltover.tl.types.messages import StickerSet as MessagesStickerSet


class Stickerset(Model):
    id: int = fields.BigIntField(pk=True)
    title: str = fields.CharField(max_length=64)
    short_name: str = fields.CharField(max_length=64, unique=True)
    access_hash: int = fields.BigIntField(default=lambda: Long.read_bytes(urandom(8)))
    owner: models.User | None = fields.ForeignKeyField("models.User", null=True)
    official: bool = fields.BooleanField(default=False)
    hash: int = fields.IntField(default=0)

    owner_id: int | None

    @classmethod
    async def from_input(
            cls, input_set: InputStickerSetEmpty | InputStickerSetID | InputStickerSetShortName | None
    ) -> Stickerset | None:
        if input_set is None or isinstance(input_set, InputStickerSetEmpty):
            return None
        elif isinstance(input_set, InputStickerSetID):
            return await Stickerset.get_or_none(id=input_set.id, access_hash=input_set.access_hash)
        elif isinstance(input_set, InputStickerSetShortName):
            return await Stickerset.get_or_none(short_name=input_set.short_name)

        # TODO: support InputStickerSetAnimatedEmoji
        # TODO: support InputStickerSetDice
        # TODO: support InputStickerSetAnimatedEmojiAnimations
        # TODO: support InputStickerSetPremiumGifts
        # TODO: support InputStickerSetEmojiGenericAnimations
        # TODO: support InputStickerSetEmojiDefaultStatuses
        # TODO: support InputStickerSetEmojiDefaultTopicIcons
        # TODO: support InputStickerSetEmojiChannelDefaultStatuses

        return None

    async def to_tl(self, user: models.User) -> StickerSet:
        installed = await models.InstalledStickerset.get_or_none(set=self, user=user)

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

            # TODO:
            thumbs=None,
            thumb_dc_id=None,
            thumb_version=None,
            thumb_document_id=None,

            masks=False,
            emojis=False,
            text_color=False,
            channel_emoji_status=False,
        )

    def documents_query(self) -> QuerySet[models.File]:
        return models.File.filter(stickerset=self).order_by("sticker_pos")

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
                await file.to_tl_document(user)
                for file in await self.documents_query()
            ],
        )
