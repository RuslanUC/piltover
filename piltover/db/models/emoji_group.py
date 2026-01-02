from __future__ import annotations

from io import BytesIO

from tortoise import Model, fields

from piltover.db import models
from piltover.db.enums import EmojiGroupType, EmojiGroupCategory
from piltover.exceptions import Unreachable
from piltover.tl import EmojiGroupPremium, EmojiGroup as TLEmojiGroup


class EmojiGroup(Model):
    id: int = fields.BigIntField(pk=True)
    category: EmojiGroupCategory = fields.IntEnumField(EmojiGroupCategory, index=True)
    type: EmojiGroupType = fields.IntEnumField(EmojiGroupType)
    position: int = fields.SmallIntField()
    name: str = fields.CharField(max_length=64)
    icon_emoji: models.File = fields.ForeignKeyField("models.File")
    emoticons: bytes | None = fields.BinaryField(null=True, default=None)

    icon_emoji_id: int

    @staticmethod
    def pack_emoticons(emoticons: list[str]) -> bytes:
        result = BytesIO()
        for emoticon in emoticons:
            emoticon_bytes = emoticon.encode("utf8")
            result.write(bytes([len(emoticon_bytes)]))
            result.write(emoticon_bytes)

        return result.getvalue()

    @staticmethod
    def unpack_emoticons(emoticons: bytes) -> list[str]:
        result = []
        emoticons = BytesIO(emoticons)
        while length := emoticons.read(1)[0]:
            result.append(emoticons.read(length).decode("utf8"))

        return result

    def to_tl(self) -> TLEmojiGroup | EmojiGroupPremium:
        if self.type is EmojiGroupType.REGULAR:
            return EmojiGroup(
                title=self.name,
                icon_emoji_id=self.icon_emoji_id,
                emoticons=self.unpack_emoticons(self.emoticons),
            )
        if self.type is EmojiGroupType.PREMIUM:
            return EmojiGroupPremium(
                title=self.name,
                icon_emoji_id=self.icon_emoji_id,
            )

        raise Unreachable

