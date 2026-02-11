from __future__ import annotations

from datetime import datetime
from io import BytesIO
from os import urandom

from loguru import logger
from tortoise import fields, Model

from piltover.db import models
from piltover.db.enums import CallDiscardReason, CALL_DISCARD_REASON_TO_TL
from piltover.exceptions import InvalidConstructorException
from piltover.tl import Long, PhoneCallDiscarded, PhoneCallProtocol, PhoneCallDiscardReasonDisconnect, PhoneConnection, \
    PhoneConnectionWebrtc
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
    duration: int | None = fields.IntField(null=True, default=None)
    protocol: bytes = fields.BinaryField()

    from_user_id: int
    from_sess_id: int
    to_user_id: int
    to_sess_id: int | None

    def protocol_tl(self) -> PhoneCallProtocol | None:
        try:
            return PhoneCallProtocol.read(BytesIO(self.protocol))
        except InvalidConstructorException as e:
            logger.opt(exception=e).error("Failed to read phone call protocol")
            return None

    def other_user_id(self, current: int) -> int:
        return self.to_user_id if current == self.from_user_id else self.from_user_id

    def other_user(self, current: models.User) -> models.User:
        return self.to_user if current.id == self.from_user_id else self.from_user

    def to_tl(self) -> EncryptedChatBase:
        if self.discard_reason is not None:
            return PhoneCallDiscarded(
                id=self.id,
                reason=CALL_DISCARD_REASON_TO_TL[self.discard_reason],
                duration=self.duration,
            )

        if (protocol := self.protocol_tl()) is None:
            return PhoneCallDiscarded(
                id=self.id,
                reason=PhoneCallDiscardReasonDisconnect(),
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
            protocol=protocol,
            connections=[
                PhoneConnectionWebrtc(
                    id=1,
                    ip="192.168.0.111",
                    ipv6="::1",
                    port=12346,
                    username="test",
                    password="test",
                    turn=True,
                    stun=True,
                ),
                PhoneConnection(
                    tcp=False,
                    id=1,
                    ip="192.168.0.111",
                    ipv6="::1",
                    port=12345,
                    peer_tag=b"0123456789abcdef",
                ),
            ],
            start_date=int(self.started_at.timestamp()) if self.started_at else None,
        )
