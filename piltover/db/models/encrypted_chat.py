from __future__ import annotations

from datetime import datetime
from os import urandom

from tortoise import fields, Model

from piltover.db import models
from piltover.tl import Long, EncryptedChat as TLEncryptedChat, EncryptedChatWaiting, EncryptedChatRequested, \
    EncryptedChatDiscarded


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

    async def to_tl(self, user: models.User, auth_id: int) -> TLEncryptedChat | EncryptedChatWaiting | EncryptedChatRequested | EncryptedChatDiscarded:
        if self.discarded:
            return EncryptedChatDiscarded(
                id=self.id,
                history_deleted=self.history_deleted,
            )

        common_kwargs = {
            "id": self.id,
            "access_hash": self.access_hash,
            "date": int(self.created_at.timestamp()),
            "admin_id": self.from_user_id,
            "participant_id": self.to_user_id,
        }

        if user.id == self.from_user_id:
            if self.to_sess_id is None:
                return EncryptedChatWaiting(**common_kwargs)
            else:
                return TLEncryptedChat(
                    **common_kwargs,
                    g_a_or_b=self.g_a if user.id == self.to_user_id else self.g_b,
                    key_fingerprint=self.key_fp,
                )

        if user.id == self.to_sess_id:
            if self.to_sess_id is None:
                return EncryptedChatRequested(
                    **common_kwargs,
                    g_a=self.g_a,
                )
            elif self.to_sess_id == auth_id:
                return TLEncryptedChat(
                    **common_kwargs,
                    g_a_or_b=self.g_a if user.id == self.to_user_id else self.g_b,
                    key_fingerprint=self.key_fp,
                )
            else:
                return EncryptedChatDiscarded(
                    id=self.id,
                    history_deleted=True,
                )

        raise RuntimeError("Unreachable")
