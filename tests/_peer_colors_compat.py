from io import BytesIO
from typing import Self

from piltover.tl.functions.help import GetPeerColors, GetPeerProfileColors
from piltover.tl.types.help import PeerColors, PeerColorOption, PeerColorOption_167, PeerColorSet, PeerColorProfileSet, \
    PeerColorsNotModified


class GetPeerColorsCompat(GetPeerColors):
    QUALNAME = GetPeerColors.__tl_name__
    RESTORE_CLS = GetPeerColors

    def __len__(self) -> int:
        return len(self.write())

    @classmethod
    def read(cls, stream: BytesIO) -> Self:
        return cls.deserialize(stream)


class GetPeerProfileColorsCompat(GetPeerProfileColors):
    QUALNAME = GetPeerProfileColors.__tl_name__
    RESTORE_CLS = GetPeerProfileColors

    def __len__(self) -> int:
        return len(self.write())

    @classmethod
    def read(cls, stream: BytesIO) -> Self:
        return cls.deserialize(stream)


class PeerColorsCompat(PeerColors):
    QUALNAME = PeerColors.__tl_name__
    RESTORE_CLS = PeerColors

    def __len__(self) -> int:
        return len(self.write())

    @classmethod
    def read(cls, stream: BytesIO) -> Self:
        return cls.deserialize(stream)


class PeerColorsNotModifiedCompat(PeerColorsNotModified):
    QUALNAME = PeerColorsNotModified.__tl_name__
    RESTORE_CLS = PeerColorsNotModified

    def __len__(self) -> int:
        return len(self.write())

    @classmethod
    def read(cls, stream: BytesIO) -> Self:
        return cls.deserialize(stream)


class PeerColorOptionCompat(PeerColorOption):
    QUALNAME = PeerColorOption.__tl_name__
    RESTORE_CLS = PeerColorOption

    def __len__(self) -> int:
        return len(self.write())

    @classmethod
    def read(cls, stream: BytesIO) -> Self:
        return cls.deserialize(stream)


class PeerColorOption_167Compat(PeerColorOption_167):
    QUALNAME = PeerColorOption_167.__tl_name__
    RESTORE_CLS = PeerColorOption_167

    def __len__(self) -> int:
        return len(self.write())

    @classmethod
    def read(cls, stream: BytesIO) -> Self:
        return cls.deserialize(stream)


class PeerColorSetCompat(PeerColorSet):
    QUALNAME = PeerColorSet.__tl_name__
    RESTORE_CLS = PeerColorSet

    def __len__(self) -> int:
        return len(self.write())

    @classmethod
    def read(cls, stream: BytesIO) -> Self:
        return cls.deserialize(stream)


class PeerColorProfileSetCompat(PeerColorProfileSet):
    QUALNAME = PeerColorProfileSet.__tl_name__
    RESTORE_CLS = PeerColorProfileSet

    def __len__(self) -> int:
        return len(self.write())

    @classmethod
    def read(cls, stream: BytesIO) -> Self:
        return cls.deserialize(stream)