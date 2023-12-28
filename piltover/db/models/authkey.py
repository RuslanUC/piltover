from tortoise import fields

from piltover.db.models._utils import Model


class AuthKey(Model):
    id: str = fields.CharField(pk=True, max_length=64)
    auth_key: bytes = fields.BinaryField()
