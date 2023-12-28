from os import urandom
from random import randint
from time import time

from tortoise import fields

from piltover.db.models._utils import Model


def gen_phone_code():
    return randint(1, 99999)


def gen_hash():
    return urandom(8).hex()


def gen_expires_at():
    return int(time()) + 5 * 60


class SentCode(Model):
    id: int = fields.BigIntField(pk=True)
    phone_number: str = fields.CharField(index=True, max_length=20)
    code: int = fields.IntField(default=gen_phone_code)
    hash: str = fields.CharField(max_length=16, default=gen_hash)
    expires_at: int = fields.BigIntField(default=gen_expires_at)
    used: bool = fields.BooleanField(default=False)

    def phone_code_hash(self) -> str:
        return (self.id & 0xFFFFFFFF).to_bytes(4).hex() + self.hash
