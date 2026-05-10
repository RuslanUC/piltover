from io import BytesIO
from typing import Self

from piltover.tl.functions.account import UpdatePersonalChannel
from piltover.tl.types.users import UserFull as UsersUserFull


class UpdatePersonalChannelCompat(UpdatePersonalChannel):
    QUALNAME = UpdatePersonalChannel.__tl_name__
    RESTORE_CLS = UpdatePersonalChannel

    def __len__(self) -> int:
        return len(self.write())

    @classmethod
    def read(cls, stream: BytesIO) -> Self:
        return cls.deserialize(stream)


class UsersUserFullCompat(UsersUserFull):
    QUALNAME = UsersUserFull.__tl_name__
    RESTORE_CLS = UsersUserFull

    def __len__(self) -> int:
        return len(self.write())

    @classmethod
    def read(cls, stream: BytesIO) -> Self:
        return cls.deserialize(stream)
