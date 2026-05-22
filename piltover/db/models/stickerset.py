from __future__ import annotations

import hashlib
import hmac
from typing import Generator, cast

from fastrand import xorshift128plus_bytes
from loguru import logger
from tortoise import Model, fields
from tortoise.expressions import Q
from tortoise.queryset import QuerySet

from piltover.cache import Cache
from piltover.config import APP_CONFIG
from piltover.db import models
from piltover.db.enums import StickerSetType, StickerSetOfficialType
from piltover.tl import InputStickerSetEmpty, InputStickerSetID, InputStickerSetShortName, Long, PhotoSize, \
    StickerPack, InputStickerSetAnimatedEmoji, InputStickerSetDice, InputStickerSetAnimatedEmojiAnimations, \
    InputStickerSetEmojiGenericAnimations, InputStickerSetEmojiDefaultStatuses, InputStickerSetEmojiDefaultTopicIcons
from piltover.tl.to_format import StickerSetToFormat
from piltover.tl.types.internal import StickerSetToFormatCommon, StickerSetToFormatForUser
from piltover.tl.types.internal_access import AccessHashPayloadStickerset
from piltover.tl.types.messages import StickerSet as MessagesStickerSet
from piltover.tl.base import InputStickerSet as InputStickerSetBase, StickerSet as TLStickerSetBase

EMOTICON_TO_DICE_ENUM = {
    "\U0001F3C0": StickerSetOfficialType.DICE_BASKETBALL,
    "\U0001F3B2": StickerSetOfficialType.DICE_DIE,
    "\U0001F3AF": StickerSetOfficialType.DICE_TARGET,
    "\u26bd": StickerSetOfficialType.DICE_FOOTBALL,
    "\u26bd\ufe0f": StickerSetOfficialType.DICE_FOOTBALL,
    "\U0001F3B0": StickerSetOfficialType.DICE_SLOTMACHINE,
    "\U0001F3B3": StickerSetOfficialType.DICE_BOWLING,
}
OFFICIAL_TL_SET_TO_ENUM = {
    InputStickerSetAnimatedEmoji: StickerSetOfficialType.ANIMATED_EMOJI,
    InputStickerSetAnimatedEmojiAnimations: StickerSetOfficialType.EMOJI_ANIMATIONS,
    InputStickerSetEmojiGenericAnimations: StickerSetOfficialType.GENERIC_ANIMATIONS,
    InputStickerSetEmojiDefaultStatuses: StickerSetOfficialType.USER_STATUSES,
    InputStickerSetEmojiDefaultTopicIcons: StickerSetOfficialType.TOPIC_ICONS,
}


def stickerset_gen_access_hash() -> int:
    return Long.read_bytes(xorshift128plus_bytes(8), signed=True)


class Stickerset(Model):
    id: int = fields.BigIntField(primary_key=True)
    title: str = fields.CharField(max_length=64)
    short_name: str | None = fields.CharField(max_length=64, unique=True, null=True)
    owner: models.User | None = fields.ForeignKeyField("models.User", null=True)
    official: bool = fields.BooleanField(default=False)
    hash: int = fields.IntField(default=0)
    type: StickerSetType = fields.IntEnumField(StickerSetType, description="")
    official_type: StickerSetOfficialType | None = fields.IntEnumField(StickerSetOfficialType, null=True, default=None, db_index=True, description="")
    deleted: bool = fields.BooleanField(default=False)
    emoji: bool = fields.BooleanField(default=False)
    masks: bool = fields.BooleanField(default=False)
    stickers_count: int = fields.SmallIntField(default=0)

    owner_id: int | None

    thumb: models.StickersetThumb | QuerySet[models.StickersetThumb] | None
    _thumb: models.StickersetThumb | None

    @classmethod
    def from_input_q(
            cls, user_id: int, auth_id: int, input_set: InputStickerSetBase | None, prefix: str | None = None,
    ) -> Q | None:
        prefix = f"{prefix}__" if prefix is not None else ""
        if input_set is None or isinstance(input_set, InputStickerSetEmpty):
            return None
        elif isinstance(input_set, InputStickerSetID):
            if not cls.check_access_hash(user_id, auth_id, input_set.id, input_set.access_hash):
                return None
            return Q(**{
                f"{prefix}id": input_set.id, f"{prefix}deleted": False,
            })
        elif isinstance(input_set, InputStickerSetShortName):
            return Q(**{f"{prefix}short_name": input_set.short_name, f"{prefix}deleted": False})
        elif isinstance(input_set, InputStickerSetDice):
            if input_set.emoticon not in EMOTICON_TO_DICE_ENUM:
                logger.warning(
                    "Invalid sticker set dice: {emoticon!r}, not in {valid}",
                    emoticon=input_set.emoticon, valid=EMOTICON_TO_DICE_ENUM.keys(),
                )
                return None
            dice_type = EMOTICON_TO_DICE_ENUM[input_set.emoticon]
            return Q(**{f"{prefix}official_type": dice_type, f"{prefix}deleted": False})
        elif type(input_set) in OFFICIAL_TL_SET_TO_ENUM:
            official_type = OFFICIAL_TL_SET_TO_ENUM[type(input_set)]
            return Q(**{f"{prefix}official_type": official_type, f"{prefix}deleted": False})

        # TODO: support InputStickerSetPremiumGifts
        # TODO: support InputStickerSetEmojiChannelDefaultStatuses

        logger.warning(f"Invalid sticker set: {input_set}")

        return None

    @classmethod
    async def from_input(
            cls, user_id: int, auth_id: int, input_set: InputStickerSetBase | None, with_thumb: bool = False,
    ) -> Stickerset | None:
        if (q := cls.from_input_q(user_id, auth_id, input_set)) is None:
            return None
        query = cls.get_or_none(q)
        if with_thumb:
            query = query.select_related("thumb", "thumb__file")
        return await query

    async def to_tl_info(self) -> StickerSetToFormatCommon:
        cache_key = self.cache_key()
        cached = await Cache.obj.get(cache_key)
        if cached is not None:
            return cached

        if self.thumb is None:
            thumb_version = None
            thumb_sizes = None
        elif isinstance(self.thumb, models.StickersetThumb):
            thumb_version = self.thumb.file_id
            thumb_sizes = [PhotoSize(type_="s", w=100, h=100, size=self.thumb.file.size)]
        else:
            raise ValueError("Stickerset thumb must be prefetched!")

        result = StickerSetToFormatCommon(
            id=self.id,
            access_hash=-1,
            title=self.title,
            short_name=self.short_name,
            official=self.official,
            creator_id=self.owner_id or 0,
            count=self.stickers_count,
            hash=self.hash,
            masks=self.masks,
            emoji=self.emoji,
            thumbs=thumb_sizes,
            thumb_version=thumb_version,
        )

        await Cache.obj.set(cache_key, result)
        return result

    async def to_tl_for_user(self, user_id: int) -> StickerSetToFormatForUser:
        cache_key = self.cache_key_for_user(user_id)
        cached = await Cache.obj.get(cache_key)
        if cached is not None:
            return cached

        info = await models.InstalledStickerset.get_or_none(
            set_id=self.id, user_id=user_id
        ).only("installed_at", "archived")

        result = StickerSetToFormatForUser(
            installed_date=int(info.installed_at.timestamp()) if info is not None else None,
            archived=info.archived if info is not None else False,
        )

        await Cache.obj.set(cache_key, result)
        return result

    async def to_tl(self, user_id: int) -> TLStickerSetBase:
        return StickerSetToFormat(
            for_user=await self.to_tl_for_user(user_id),
            info=await self.to_tl_info(),
        )

    # TODO: also add documents_query_cls that takes stickerset id
    def documents_query(self) -> QuerySet[models.File]:
        return models.File.filter(stickerset=self).order_by("sticker_pos")

    def gen_for_hash(self, stickers: list[models.File]) -> Generator[str | int, None, None]:
        yield self.id
        yield self.title

        for sticker in stickers:
            yield sticker.id
            yield cast(int, sticker.sticker_pos)
            yield cast(str, sticker.sticker_alt)

    async def to_tl_messages(self, user_id: int) -> MessagesStickerSet:
        cache_key = self.cache_key_messages()
        cached = await Cache.obj.get(cache_key)
        if cached is not None:
            return cached

        files = await self.documents_query()

        documents = []
        packs: dict[str, StickerPack] = {}

        for file in files:
            documents.append(file.to_tl_document())
            if not self.emoji:
                continue
            if file.sticker_alt not in packs:
                packs[file.sticker_alt] = StickerPack(emoticon=file.sticker_alt, documents=[])
            packs[file.sticker_alt].documents.append(file.id)

        result = MessagesStickerSet(
            set=await self.to_tl(user_id),
            packs=list(packs.values()),
            keywords=[],  # TODO: add support for keywords
            documents=documents,
        )

        await Cache.obj.set(cache_key, result)
        return result

    def cache_key(self) -> str:
        return f"stickerset:{self.id}:{self.hash}"

    def cache_key_messages(self) -> str:
        return f"stickerset-messages:{self.id}:{self.hash}"

    def cache_key_for_user(self, user_id: int) -> str:
        return f"stickerset-for-user:{self.id}:{user_id}"

    @staticmethod
    def make_access_hash(user: int, auth: int, set_id: int) -> int:
        to_sign = AccessHashPayloadStickerset(this_user_id=user, set_id=set_id, auth_id=auth).write()
        digest = hmac.new(APP_CONFIG.hmac_key, to_sign, hashlib.sha256).digest()
        return Long.read_bytes(digest[-8:])

    @classmethod
    def check_access_hash(cls, user: int, auth: int, set_id: int, access_hash: int) -> bool:
        return cls.make_access_hash(user, auth, set_id) == access_hash
