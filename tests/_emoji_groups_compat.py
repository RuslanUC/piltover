from io import BytesIO
from typing import Self

from piltover.tl import EmojiGroupGreeting, EmojiGroupPremium
from piltover.tl.functions.messages import GetEmojiStickerGroups


class GetEmojiStickerGroupsCompat(GetEmojiStickerGroups):
    QUALNAME = GetEmojiStickerGroups.__tl_name__
    RESTORE_CLS = GetEmojiStickerGroups

    def __len__(self) -> int:
        return len(self.write())

    @classmethod
    def read(cls, stream: BytesIO) -> Self:
        return cls.deserialize(stream)


class EmojiGroupGreetingCompat(EmojiGroupGreeting):
    QUALNAME = EmojiGroupGreeting.__tl_name__
    RESTORE_CLS = EmojiGroupGreeting

    def __len__(self) -> int:
        return len(self.write())

    @classmethod
    def read(cls, stream: BytesIO) -> Self:
        return cls.deserialize(stream)


class EmojiGroupPremiumCompat(EmojiGroupPremium):
    QUALNAME = EmojiGroupPremium.__tl_name__
    RESTORE_CLS = EmojiGroupPremium

    def __len__(self) -> int:
        return len(self.write())

    @classmethod
    def read(cls, stream: BytesIO) -> Self:
        return cls.deserialize(stream)
