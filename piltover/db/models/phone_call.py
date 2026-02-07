from __future__ import annotations

from datetime import datetime
from os import urandom

from tortoise import fields, Model

from piltover.db import models
from piltover.db.enums import CallDiscardReason, CALL_DISCARD_REASON_TO_TL
from piltover.tl import Long, PhoneCallDiscarded
from piltover.tl.base import EncryptedChat as EncryptedChatBase
from piltover.tl.to_format import PhoneCallToFormat


class PhoneCall(Model):
    id: int = fields.BigIntField(pk=True)
    access_hash: int = fields.BigIntField(default=lambda: Long.read_bytes(urandom(8), signed=True))
    created_at: datetime = fields.DatetimeField(auto_now_add=True)
    started_at: datetime | None = fields.DatetimeField(null=True, default=None)
    from_user: models.User = fields.ForeignKeyField("models.User", related_name="call_from_user")
    from_sess: models.UserAuthorization = fields.ForeignKeyField("models.UserAuthorization", related_name="call_from_sess")
    to_user: models.User = fields.ForeignKeyField("models.User", related_name="call_to_user")
    to_sess: models.UserAuthorization | None = fields.ForeignKeyField("models.UserAuthorization", related_name="call_to_sess", null=True)
    g_a_hash: bytes = fields.BinaryField()
    g_a: bytes | None = fields.BinaryField(null=True, default=None)
    g_b: bytes | None = fields.BinaryField(null=True, default=None)
    key_fp: int | None = fields.BigIntField(null=True, default=None)
    discard_reason: CallDiscardReason | None = fields.IntEnumField(CallDiscardReason, null=True, default=None)

    from_user_id: int
    from_sess_id: int
    to_user_id: int
    to_sess_id: int | None

    def to_tl(self) -> EncryptedChatBase:
        if self.discard_reason is not None:
            return PhoneCallDiscarded(
                id=self.id,
                reason=CALL_DISCARD_REASON_TO_TL[self.discard_reason],
            )

        return PhoneCallToFormat(
            id=self.id,
            access_hash=self.access_hash,
            date=int(self.created_at.timestamp()),
            admin_id=self.from_user_id,
            participant_id=self.to_user_id,
            admin_sess_id=self.from_sess_id,
            participant_sess_id=self.to_sess_id,
            g_a=self.g_a,
            g_a_hash=self.g_a_hash,
            g_b=self.g_b,
            key_fingerprint=self.key_fp,
            protocol=None,
            connections=None,
            start_date=int(self.started_at.timestamp()) if self.started_at else None,
        )
