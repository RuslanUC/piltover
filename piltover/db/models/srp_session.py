from __future__ import annotations

from os import urandom
from time import time

from tortoise import fields

from piltover.db import models
from piltover.db.models._utils import Model
from piltover.utils import gen_safe_prime
from piltover.utils.srp import SRP_K, btoi, itob


def gen_b() -> bytes:
    return urandom(256)


def gen_created_at() -> int:
    return int(time())


class SrpSession(Model):
    id: int = fields.BigIntField(pk=True)
    priv_b: bytes = fields.BinaryField(default=gen_b)
    created_at: int = fields.BigIntField(default=gen_created_at)
    password: models.UserPassword = fields.ForeignKeyField("models.UserPassword")

    def pub_B(self) -> bytes:
        p, g = gen_safe_prime()
        k_v: int = (SRP_K * btoi(self.password.password)) % p
        return itob((k_v + (pow(g, btoi(self.priv_b), p))) % p)

    @classmethod
    async def get_current(cls, password: models.UserPassword) -> SrpSession:
        session, _ = await SrpSession.get_or_create(
            password=password,
            created_at__gt=int(time() - 1800),
            defaults={"created_at": int(time())}
        )
        await session.fetch_related("password")

        return session
