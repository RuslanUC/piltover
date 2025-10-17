from os import urandom

from tortoise import Model, fields

from piltover.tl import FutureSalt


def gen_salt() -> int:
    return int.from_bytes(urandom(8)) >> 1


class ServerSalt(Model):
    id: int = fields.BigIntField(pk=True)
    salt: int = fields.BigIntField(default=gen_salt)

    def to_tl(self) -> FutureSalt:
        return FutureSalt(
            valid_since=self.id * 60 * 60,
            valid_until=(self.id + 1) * 60 * 60,
            salt=self.salt,
        )
