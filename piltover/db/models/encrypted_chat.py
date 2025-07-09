from __future__ import annotations

from datetime import datetime
from os import urandom

from tortoise import fields, Model

from piltover.db import models
from piltover.tl import Long, EncryptedChat as TLEncryptedChat, EncryptedChatWaiting, EncryptedChatRequested


class EncryptedChat(Model):
    id: int = fields.BigIntField(pk=True)
    access_hash: int = fields.BigIntField(default=lambda: Long.read_bytes(urandom(8), signed=True))
    created_at: datetime = fields.DatetimeField(auto_now_add=True)
    from_user: models.User = fields.ForeignKeyField("models.User", related_name="from_user")
    from_sess: models.UserAuthorization = fields.ForeignKeyField("models.UserAuthorization", related_name="from_sess")
    to_user: models.User = fields.ForeignKeyField("models.User", related_name="to_user")
    to_sess: models.UserAuthorization | None = fields.ForeignKeyField("models.UserAuthorization", related_name="to_sess", null=True)
    dh_version: int = fields.IntField()
    g_a: bytes = fields.BinaryField()
    g_b: bytes = fields.BinaryField()
    key_fp: int | None = fields.BigIntField(null=True, default=None)
    discarded: bool = fields.BooleanField(default=False)

    from_user_id: int
    from_sess_id: int
    to_user_id: int
    to_sess_id: int | None

    # TODO: unique from_user-to_user pairs?
    #class Meta:
    #    unique_together = (
    #        ("from_user", "to_user"),
    #    )

    async def  to_tl(self, user: models.User) -> TLEncryptedChat | EncryptedChatWaiting | EncryptedChatRequested:
        if self.to_sess_id is not None:
            return TLEncryptedChat(
                id=self.id,
                access_hash=self.access_hash,
                date=int(self.created_at.timestamp()),
                admin_id=self.from_user_id,
                participant_id=self.to_user_id,
                g_a_or_b=self.g_a if user.id == self.to_user_id else self.g_b,
                key_fingerprint=self.key_fp,
            )

        if self.to_sess_id is None and user.id == self.from_user_id:
            return EncryptedChatWaiting(
                id=self.id,
                access_hash=self.access_hash,
                date=int(self.created_at.timestamp()),
                admin_id=self.from_user_id,
                participant_id=self.to_user_id,
            )
        elif self.to_sess_id is None and user.id == self.to_user_id:
            return EncryptedChatRequested(
                id=self.id,
                access_hash=self.access_hash,
                date=int(self.created_at.timestamp()),
                admin_id=self.from_user_id,
                participant_id=self.to_user_id,
                g_a=self.g_a,
            )

        raise RuntimeError("Unreachable")
