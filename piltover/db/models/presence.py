from __future__ import annotations

from datetime import datetime, UTC, timedelta
from enum import auto, Enum
from time import time

from tortoise import fields, Model

from piltover.db import models
from piltover.db.enums import UserStatus, PrivacyRuleKeyType
from piltover.tl import UserStatusEmpty, UserStatusOffline, UserStatusOnline, UserStatusRecently, UserStatusLastWeek, \
    UserStatusLastMonth

TLUserStatus = UserStatusEmpty | UserStatusOnline | UserStatusOffline | UserStatusRecently | UserStatusLastWeek \
               | UserStatusLastMonth

EMPTY = UserStatusEmpty()
RECENTLY = UserStatusRecently()
LAST_WEEK = UserStatusLastWeek()
LAST_MONTH = UserStatusLastMonth()


class _PresenceMissing(Enum):
    MISSING = auto()


_MISSING = _PresenceMissing.MISSING


class Presence(Model):
    id: int = fields.BigIntField(pk=True)
    user: models.User = fields.OneToOneField("models.User")
    status: UserStatus = fields.IntEnumField(UserStatus, default=UserStatus.OFFLINE, description="")
    last_seen: datetime = fields.DatetimeField(default_add=True)

    user_id: int

    EMPTY = EMPTY
    RECENTLY = RECENTLY
    LAST_WEEK = LAST_WEEK
    LAST_MONTH = LAST_MONTH

    async def to_tl(self, user: models.User | None, has_access: bool | _PresenceMissing = _MISSING) -> TLUserStatus:
        now = datetime.now(UTC)
        delta = now - self.last_seen
        if delta < timedelta(seconds=30):
            return UserStatusOnline(expires=int(time() + 30))

        if has_access is _MISSING:
            has_access = await models.PrivacyRule.has_access_to(user, self.user_id, PrivacyRuleKeyType.STATUS_TIMESTAMP)

        return self.to_tl_noprivacycheck(has_access)

    def to_tl_noprivacycheck(self, has_access: bool) -> TLUserStatus:
        now = datetime.now(UTC)
        delta = now - self.last_seen
        if delta < timedelta(seconds=30):
            return UserStatusOnline(expires=int(time() + 30))

        if has_access:
            return UserStatusOffline(was_online=int(self.last_seen.timestamp()))

        if delta <= timedelta(days=3):
            return RECENTLY
        if delta <= timedelta(days=7):
            return LAST_WEEK
        if delta <= timedelta(days=28):
            return LAST_MONTH

        return EMPTY

    @classmethod
    async def to_tl_or_empty(
            cls, user: models.User, current_user: models.User, presence: Presence | _PresenceMissing | None = _MISSING,
            has_access: bool | _PresenceMissing = _MISSING,
    ) -> TLUserStatus:
        if presence is _MISSING:
            presence = await Presence.get_or_none(user=user)

        if presence is not None:
            if has_access is _MISSING:
                return await presence.to_tl(current_user)
            return presence.to_tl_noprivacycheck(has_access)

        return EMPTY

    @classmethod
    async def update_to_now(cls, user: models.User, status: UserStatus = UserStatus.ONLINE) -> Presence:
        if user.bot:
            raise RuntimeError("Can't set presence for bot")

        last_seen = datetime.now(UTC)
        presence, created = await cls.get_or_create(user=user, defaults={"status": status, "last_seen": last_seen})
        if not created:
            presence.last_seen = last_seen
            await presence.save(update_fields=["last_seen"])

        return presence
