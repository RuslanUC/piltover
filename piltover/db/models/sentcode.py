from __future__ import annotations

from enum import IntEnum
from random import randint
from time import time
from uuid import UUID, uuid4

from tortoise import fields, Model
from tortoise.expressions import Q

from piltover.db import models
from piltover.exceptions import ErrorRpc
from piltover.tl import Long


class PhoneCodePurpose(IntEnum):
    SIGNIN = 1
    SIGNUP = 2
    CHANGE_NUMBER = 3
    DELETE_ACCOUNT = 4


class SentCode(Model):
    CODE_HASH_SIZE = len(Long.write(0).hex() + uuid4().hex)

    @staticmethod
    def gen_phone_code():
        return randint(1, 99999)

    @staticmethod
    def gen_expires_at():
        return int(time()) + 5 * 60

    id: int = fields.BigIntField(pk=True)
    phone_number: str = fields.CharField(max_length=20)
    code: int = fields.IntField(default=gen_phone_code)
    hash: UUID = fields.UUIDField(default=uuid4)
    expires_at: int = fields.BigIntField(default=gen_expires_at)
    used: bool = fields.BooleanField(default=False)
    purpose: PhoneCodePurpose = fields.IntEnumField(PhoneCodePurpose)
    user: models.User | None = fields.ForeignKeyField("models.User", null=True, default=None)

    def phone_code_hash(self) -> str:
        return Long.write(self.id).hex() + self.hash.hex

    @classmethod
    async def get_(cls, number: str, code_hash: str, purpose: PhoneCodePurpose | None) -> SentCode | None:
        code_id = Long.read_bytes(bytes.fromhex(code_hash[:16]))
        code_hash = UUID(code_hash[16:])

        query = Q(id=code_id, hash=code_hash, phone_number=number, used=False)
        if purpose is not None:
            query &= Q(purpose=purpose)

        return await SentCode.get_or_none(query)

    async def check_raise(self, code: str | None) -> None:
        if code is not None and self.code != int(code):
            raise ErrorRpc(error_code=400, error_message="PHONE_CODE_INVALID")
        if self.expires_at < time():
            await self.delete()
            raise ErrorRpc(error_code=400, error_message="PHONE_CODE_EXPIRED")

    @classmethod
    async def check_raise_cls(cls, sent_code: SentCode | None, code: str | None) -> None:
        if sent_code is None:
            raise ErrorRpc(error_code=400, error_message="PHONE_CODE_INVALID")
        await sent_code.check_raise(code)
