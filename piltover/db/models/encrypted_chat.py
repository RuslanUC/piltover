from __future__ import annotations

from datetime import datetime
from os import urandom

from tortoise import fields, Model

from piltover.db import models
from piltover.tl import Long, EncryptedChatDiscarded
from piltover.tl.base import EncryptedChat as EncryptedChatBase
from piltover.tl.to_format import EncryptedChatToFormat


class EncryptedChat(Model):
    id: int = fields.BigIntField(pk=True)
    access_hash: int = fields.BigIntField(default=lambda: Long.read_bytes(urandom(8), signed=True))
    created_at: datetime = fields.DatetimeField(auto_now_add=True)
    from_user: models.User = fields.ForeignKeyField("models.User", related_name="enc_from_user")
    from_sess: models.UserAuthorization = fields.ForeignKeyField("models.UserAuthorization", related_name="enc_from_sess")
    to_user: models.User = fields.ForeignKeyField("models.User", related_name="enc_to_user")
    to_sess: models.UserAuthorization | None = fields.ForeignKeyField("models.UserAuthorization", related_name="enc_to_sess", null=True)
    dh_version: int = fields.IntField()
    g_a: bytes = fields.BinaryField()
    g_b: bytes = fields.BinaryField()
    key_fp: int | None = fields.BigIntField(null=True, default=None)
    discarded: bool = fields.BooleanField(default=False)
    history_deleted: bool = fields.BooleanField(default=False)

    from_user_id: int
    from_sess_id: int
    to_user_id: int
    to_sess_id: int | None

    # TODO: unique from_user-to_user pairs?
    #class Meta:
    #    unique_together = (
    #        ("from_user", "to_user"),
    #    )

    def to_tl(self) -> EncryptedChatBase:
        if self.discarded:
            return EncryptedChatDiscarded(
                id=self.id,
                history_deleted=self.history_deleted,
            )

        return EncryptedChatToFormat(
            id=self.id,
            access_hash=self.access_hash,
            date=int(self.created_at.timestamp()),
            admin_id=self.from_user_id,
            participant_id=self.to_user_id,
            admin_sess_id=self.from_sess_id,
            participant_sess_id=self.to_sess_id,
            g_a=self.g_a,
            g_b=self.g_b or None,
            key_fingerprint=self.key_fp,
        )
