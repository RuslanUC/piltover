from __future__ import annotations

from datetime import datetime, UTC, timedelta
from time import time

from tortoise import fields, Model

from piltover.db import models
from piltover.db.enums import UserStatus
from piltover.tl import UserStatusEmpty, UserStatusOffline, UserStatusOnline, UserStatusRecently, UserStatusLastWeek, \
    UserStatusLastMonth

TLUserStatus = UserStatusEmpty | UserStatusOnline | UserStatusOffline | UserStatusRecently | UserStatusLastWeek \
               | UserStatusLastMonth

EMPTY = UserStatusEmpty()
RECENTLY = UserStatusRecently()
LAST_WEEK = UserStatusLastWeek()
LAST_MONTH = UserStatusLastMonth()

class Presence(Model):
    id: int = fields.BigIntField(pk=True)
    user: models.User = fields.ForeignKeyField("models.User", unique=True)
    status: UserStatus = fields.IntEnumField(UserStatus, default=UserStatus.OFFLINE)
    last_seen: datetime = fields.DatetimeField(default_add=True)

    async def to_tl(self, user: models.User) -> TLUserStatus:
        now = datetime.now(UTC)
        delta = now - self.last_seen
        if delta < timedelta(seconds=30):
            return UserStatusOnline(expires=int(time() + 30))

        # TODO: return UserStatusOffline(was_online=...) if user is allowed to see self.user's last online time
        if delta < timedelta(days=3):
            return RECENTLY
        if delta <= timedelta(days=7):
            return LAST_WEEK
        if delta <= timedelta(days=28):
            return LAST_MONTH

        return EMPTY

    @classmethod
    async def to_tl_or_empty(cls, user: models.User, current_user: models.User) -> TLUserStatus:
        if (presence := await Presence.get_or_none(user=user)) is not None:
            return await presence.to_tl(current_user)

        return EMPTY

    @classmethod
    async def update_to_now(cls, user: models.User, status: UserStatus = UserStatus.ONLINE) -> Presence:
        last_seen = datetime.now(UTC)
        presence, created = await cls.get_or_create(user=user, defaults={"status": status, "last_seen": last_seen})
        if not created:
            presence.last_seen = last_seen
            await presence.save(update_fields=["last_seen"])

        return presence
