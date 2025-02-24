from __future__ import annotations

from os import urandom

from tortoise import fields, Model

from piltover.db import models
from piltover.tl import SecurePasswordKdfAlgoSHA512, \
    PasswordKdfAlgoSHA256SHA256PBKDF2HMACSHA512iter100000SHA256ModPow
from piltover.tl.types.account import Password as TLPassword
from piltover.utils import gen_safe_prime
from piltover.utils.srp import itob


def gen_salt1() -> bytes:
    return urandom(8)


def gen_salt2() -> bytes:
    return urandom(16)


class UserPassword(Model):
    id: int = fields.BigIntField(pk=True)
    salt1: bytes = fields.BinaryField(default=gen_salt1)  # 8 - 40 bytes
    salt2: bytes = fields.BinaryField(default=gen_salt2)  # 16 bytes
    password: bytes | None = fields.BinaryField(null=True, default=None)  # 256 bytes
    hint: str | None = fields.CharField(max_length=120, null=True, default=None)
    user: models.User = fields.ForeignKeyField("models.User", unique=True)

    async def to_tl(self) -> TLPassword:
        p, g = gen_safe_prime()
        current = None
        srp_B = None
        srp_id = None
        if self.password is not None:
            current = PasswordKdfAlgoSHA256SHA256PBKDF2HMACSHA512iter100000SHA256ModPow(
                salt1=self.salt1,
                salt2=self.salt2,
                g=g,
                p=itob(p),
            )
            session = await models.SrpSession.get_current(self)
            srp_B = session.pub_B()
            srp_id = session.id

        return TLPassword(
            has_password=self.password is not None,
            has_recovery=False,
            has_secure_values=False,
            new_algo=PasswordKdfAlgoSHA256SHA256PBKDF2HMACSHA512iter100000SHA256ModPow(
                salt1=self.salt1[:8],
                salt2=self.salt2,
                g=g,
                p=itob(p),
            ),
            new_secure_algo=SecurePasswordKdfAlgoSHA512(salt=urandom(8)),
            secure_random=urandom(256),
            current_algo=current,
            hint=self.hint,
            srp_B=srp_B,
            srp_id=srp_id,
        )
