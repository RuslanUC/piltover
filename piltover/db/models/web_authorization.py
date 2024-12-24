from base64 import urlsafe_b64encode
from os import urandom
from time import time

from tortoise import fields, Model

from piltover.db import models


def gen_password() -> str:
    return urlsafe_b64encode(urandom(8)).decode("utf8").strip("=")


def gen_hash() -> str:
    return urandom(16).hex()


def gen_expires_at():
    return int(time()) + 5 * 60


class WebAuthorization(Model):
    id: int = fields.BigIntField(pk=True)
    phone_number: str = fields.CharField(index=True, max_length=20)
    password: str = fields.CharField(max_length=16, default=gen_password)
    random_hash: str = fields.CharField(max_length=32, default=gen_hash)
    expires_at: int = fields.BigIntField(default=gen_expires_at)
    user: models.User | None = fields.ForeignKeyField("models.User", null=True, default=None)
