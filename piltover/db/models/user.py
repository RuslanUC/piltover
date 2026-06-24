from __future__ import annotations

import hashlib
import hmac
from datetime import date, datetime, UTC, timedelta
from enum import auto, Enum
from time import time
from typing import Iterable, Self, cast, Collection

from tortoise import fields, Model
from tortoise.expressions import Q, F
from tortoise.queryset import QuerySet
from tortoise.transactions import in_transaction

from piltover.config import APP_CONFIG
from piltover.cache import Cache
from piltover.context import request_ctx
from piltover.db import models
from piltover.db.enums import PrivacyRuleKeyType
from piltover.db.models.utils import MISSING, Missing
from piltover.exceptions import Unreachable, ErrorRpc
from piltover.tl import UserProfilePhotoEmpty, PhotoEmpty, Birthday, Long, InputUser, UserStatusEmpty, \
    UserStatusRecently, UserStatusLastWeek, UserStatusLastMonth, UserStatusOnline, UserStatusOffline
from piltover.tl.to_format import UserToFormat
from piltover.tl.types import User as TLUser, PeerColor, PeerUser, InputPeerSelf, InputPeerUser, InputUserSelf
from piltover.tl.base import User as TLUserBase, UserStatus as TLUserStatusBase
from piltover.tl.types.internal_access import AccessHashPayloadUser
from piltover.utils import SingleElementList


class _Missing(Enum):
    MISSING = auto()


_MISSING = _Missing.MISSING
_PROFILE_PHOTO_EMPTY = UserProfilePhotoEmpty()
_PHOTO_EMPTY = PhotoEmpty(id=0)

STATUS_EMPTY = UserStatusEmpty()
STATUS_RECENTLY = UserStatusRecently()
STATUS_LAST_WEEK = UserStatusLastWeek()
STATUS_LAST_MONTH = UserStatusLastMonth()


class User(Model):
    id: int = fields.BigIntField(primary_key=True)
    phone_number: str | None = fields.CharField(unique=True, max_length=20, null=True)
    first_name: str = fields.CharField(max_length=128)
    last_name: str | None = fields.CharField(max_length=128, null=True, default=None)
    lang_code: str = fields.CharField(max_length=8, default="en")
    about: str | None = fields.CharField(max_length=240, null=True, default=None)
    ttl_days: int = fields.IntField(default=365)
    birthday: date | None = fields.DateField(null=True, default=None)
    bot: bool = fields.BooleanField(default=False)
    system: bool = fields.BooleanField(default=False)
    deleted: bool = fields.BooleanField(default=False)
    accent_color: models.PeerColorOption | None = fields.ForeignKeyField("models.PeerColorOption", null=True, default=None, related_name="accent")
    profile_color: models.PeerColorOption | None = fields.ForeignKeyField("models.PeerColorOption", null=True, default=None, related_name="profile")
    history_ttl_days: int = fields.SmallIntField(default=0)
    read_dates_private: bool = fields.BooleanField(default=False)
    version: int = fields.IntField(default=0)
    pts: int = fields.BigIntField(default=0)
    last_seen: datetime = fields.DatetimeField(auto_now_add=True)

    accent_color_id: int | None
    profile_color_id: int | None

    username: models.Username | QuerySet[models.Username] | None
    background_emojis: models.UserBackgroundEmojis | QuerySet[models.UserBackgroundEmojis] | None
    emoji_status: models.UserEmojiStatus | QuerySet[models.UserEmojiStatus] | None
    bot_info: models.BotInfo | QuerySet[models.BotInfo] | None

    _username: models.Username | None

    cached_username: models.Username | None | _Missing = _MISSING

    _CACHE_VERSION = 1

    @property
    def background_emojis_prefetched(self) -> bool:
        return self.background_emojis is None or isinstance(self.background_emojis, models.UserBackgroundEmojis)

    @property
    def bot_info_prefetched(self) -> bool:
        return isinstance(self.bot_info, models.BotInfo)

    @property
    def emoji_status_prefetched(self) -> bool:
        return self.emoji_status is None or isinstance(self.emoji_status, models.UserEmojiStatus)

    def _cache_key(self) -> str:
        return f"user:{self.id}:{self.version}:{self._CACHE_VERSION}"

    async def get_username(self) -> models.Username | None:
        if self.cached_username is _MISSING:
            self.cached_username = await models.Username.get_or_none(user=self)

        return self.cached_username

    async def get_raw_username(self) -> str | None:
        username = await self.get_username()
        if username is None:
            return None
        return username.username

    async def get_db_current_photo(self) -> models.UserPhoto | None:
        return await models.UserPhoto.get_or_none(user=self, current=True).select_related("file").only(
            *models.UserPhoto.ONLY_FIELDS,
        )

    async def get_db_photos(self) -> tuple[models.UserPhoto | None, models.UserPhoto | None]:
        # TODO: also fetch personal_photo (when will be implemented)

        current = None
        fallback = None

        photos = await models.UserPhoto.filter(
            Q(current=True, fallback=True, join_type=Q.OR), user=self
        ).select_related("file").only(*models.UserPhoto.ONLY_FIELDS, "current", "fallback")
        for photo in photos:
            if photo.current:
                current = photo
            elif photo.fallback:
                fallback = photo
            else:
                raise Unreachable

        return current, fallback

    async def to_tl(self, *, userphoto: models.UserPhoto | None | _Missing = _MISSING) -> TLUserBase:
        if self.deleted:
            return TLUser(
                id=self.id,
                is_self=False,
                access_hash=0,
                deleted=True,
            )

        cache_key = self._cache_key()

        presence_last_seen = None if self.bot else int(self.last_seen.timestamp())

        if (cached := await Cache.obj.get(cache_key)) is not None:
            if cached.last_seen != presence_last_seen:
                cached.last_seen = presence_last_seen
                await Cache.obj.set(cache_key, cached)
            return cached

        # TODO: min (https://core.telegram.org/api/min)

        username: models.Username | None
        if self.username is None or isinstance(self.username, models.Username):
            username = self.username
        else:
            username = self._username = await self.username

        if self.background_emojis is None or isinstance(self.background_emojis, models.UserBackgroundEmojis):
            emojis = self.background_emojis
        else:
            emojis = await models.UserBackgroundEmojis.get_or_none(user=self)

        color = None
        profile_color = None
        if self.accent_color_id is not None or (emojis is not None and emojis.accent_emoji_id is not None):
            color = PeerColor(
                color=self.accent_color_id,
                background_emoji_id=emojis.accent_emoji_id if emojis is not None else None,
            )
        if self.profile_color_id is not None or (emojis is not None and emojis.profile_emoji_id is not None):
            profile_color = PeerColor(
                color=self.profile_color_id,
                background_emoji_id=emojis.profile_emoji_id if emojis is not None else None,
            )

        bot_info_version = None
        if self.bot:
            bot_info_version = await models.BotInfo.filter(user=self).first().values_list("version", flat=True)
            bot_info_version = bot_info_version or 1

        photo = None
        if userphoto is _MISSING:
            userphoto = await self.get_db_current_photo()
        if userphoto is not None:
            photo = userphoto.to_tl_profile()

        emoji_status = None
        if not self.bot:
            if self.emoji_status is None or isinstance(self.emoji_status, models.UserEmojiStatus):
                emoji_status = self.emoji_status
            else:
                emoji_status = await models.UserEmojiStatus.get_or_none(user_id=self.id)

        result = UserToFormat(
            id=self.id,
            first_name=self.first_name,
            last_name=self.last_name,
            username=username.username if username is not None else None,
            phone=self.phone_number,
            lang_code=self.lang_code,
            photo=photo,
            bot=self.bot,
            bot_info_version=bot_info_version,
            color=color,
            profile_color=profile_color,
            emoji_status=emoji_status.to_tl() if emoji_status is not None else None,
            last_seen=presence_last_seen,
        )

        await Cache.obj.set(cache_key, result)
        return result

    @classmethod
    async def to_tl_bulk(cls, users: Iterable[models.User]) -> list[TLUserBase]:
        if not users:
            return []

        cached_users = {
            cached.id: cached
            for cached in await Cache.obj.multi_get([user._cache_key() for user in users])
            if cached is not None
        }

        all_ids = [user.id for user in users if user.id not in cached_users]
        user_ids = [user.id for user in users if not user.bot and user.id not in cached_users]
        bot_ids = [user.id for user in users if user.bot and user.id not in cached_users]

        if all_ids:
            usernames = {
                user_id: username
                for user_id, username in await models.Username.filter(
                    user_id__in=all_ids,
                ).values_list("user_id", "username")
            }
        else:
            usernames = {}

        if user_ids:
            background_emojis = {
                emojis.user_id: emojis
                for emojis in await models.UserBackgroundEmojis.filter(
                    user_id__in=[
                        user.id
                        for user in users
                        if (
                                not user.bot
                                and user.id not in cached_users
                                and not user.background_emojis_prefetched
                        )
                    ],
                )
            }
            for user in users:
                if user.background_emojis_prefetched:
                    background_emojis[user.id] = cast(models.UserBackgroundEmojis, user.background_emojis)
        else:
            background_emojis = {}

        if bot_ids:
            bot_versions = {
                user_id: version
                for user_id, version in await models.BotInfo.filter(
                    user_id__in=[
                        user.id
                        for user in users
                        if (
                                user.bot
                                and user.id not in cached_users
                                and not user.bot_info_prefetched
                        )
                    ],
                ).values_list("user_id", "version")
            }
            for user in users:
                if user.bot_info_prefetched:
                    bot_versions[user.id] = user.bot_info.version
        else:
            bot_versions = {}

        if all_ids:
            photos = {
                photo.user_id: photo
                for photo in await models.UserPhoto.filter(
                    user_id__in=all_ids, current=True,
                ).select_related("file")
            }
        else:
            photos = {}

        if user_ids:
            emoji_statuses = {
                status.user_id: status
                for status in await models.UserEmojiStatus.filter(
                    user_id__in=[
                        user.id
                        for user in users
                        if (
                                not user.bot
                                and user.id not in cached_users
                                and not user.emoji_status_prefetched
                        )
                    ],
                )
            }
            for user in users:
                if user.emoji_status_prefetched:
                    emoji_statuses[user.id] = cast(models.UserEmojiStatus, user.emoji_status)
        else:
            emoji_statuses = {}

        tl = []
        to_cache = []

        for user in users:
            if user.id in cached_users:
                tl.append(cached_users[user.id])
                continue

            emojis = background_emojis.get(user.id)

            color = None
            profile_color = None
            if user.accent_color_id is not None or (emojis is not None and emojis.accent_emoji_id is not None):
                color = PeerColor(
                    color=user.accent_color_id,
                    background_emoji_id=emojis.accent_emoji_id if emojis is not None else None,
                )
            if user.profile_color_id is not None or (emojis is not None and emojis.profile_emoji_id is not None):
                profile_color = PeerColor(
                    color=user.profile_color_id,
                    background_emoji_id=emojis.profile_emoji_id if emojis is not None else None,
                )

            emoji_status = emoji_statuses.get(user.id)

            tl.append(UserToFormat(
                id=user.id,
                first_name=user.first_name,
                last_name=user.last_name,
                username=usernames.get(user.id),
                phone=user.phone_number,
                lang_code=user.lang_code,
                photo=photos[user.id].to_tl_profile() if user.id in photos else None,
                bot=user.bot,
                bot_info_version=bot_versions.get(user.id, 1) if user.bot else None,
                color=color,
                profile_color=profile_color,
                emoji_status=emoji_status.to_tl() if emoji_status is not None else None,
                last_seen=int(user.last_seen.timestamp()) if not user.bot else None,
            ))

            to_cache.append((user._cache_key(), tl[-1]))

        if to_cache:
            await Cache.obj.multi_set(to_cache)

        return tl

    async def to_tl_maybecached(self) -> TLUserBase:
        cached_user = await Cache.obj.get(self._cache_key())
        if cached_user is not None:
            return cached_user

        await self.refresh_from_db()
        return await self.to_tl()

    @classmethod
    async def to_tl_bulk_maybecached(cls, users: Iterable[models.User]) -> list[TLUserBase]:
        if not users:
            return []

        result = await Cache.obj.multi_get([user._cache_key() for user in users])

        non_cached = [user for user, cached in zip(users, result) if cached is None]
        if not non_cached:
            return result

        non_cached_by_ids = {user.id: user for user in non_cached}

        objs = await User.filter(id__in=list(non_cached_by_ids.keys()))
        if len(non_cached_by_ids) != len(objs):
            raise Unreachable

        for obj in objs:
            user = non_cached_by_ids[obj.id]
            for field in User._meta.db_fields:
                setattr(user, field, getattr(obj, field, None))

        tl_users = {
            tl_user.id: tl_user
            for tl_user in await User.to_tl_bulk(non_cached)
        }

        for idx, (user, cached) in enumerate(zip(users, result)):
            if cached is None:
                result[idx] = tl_users[user.id]

        return result

    async def to_tl_birthday(self, user: User) -> Birthday | None:
        if self.birthday is None or not await models.PrivacyRule.has_access_to(user, self, PrivacyRuleKeyType.BIRTHDAY):
            return None

        return self.to_tl_birthday_noprivacycheck()

    def to_tl_birthday_noprivacycheck(self) -> Birthday | None:
        if self.birthday is None:
            return None

        return Birthday(
            day=self.birthday.day,
            month=self.birthday.month,
            year=self.birthday.year if self.birthday.year != 1900 else None,
        )

    @staticmethod
    def make_access_hash(user: int, auth: int, target: int) -> int:
        to_sign = AccessHashPayloadUser(this_user_id=user, user_id=target, auth_id=auth).write()
        digest = hmac.new(APP_CONFIG.hmac_key, to_sign, hashlib.sha256).digest()
        return Long.read_bytes(digest[-8:])

    @staticmethod
    def check_access_hash(user: int, auth: int, target: int, access_hash: int) -> bool:
        return User.make_access_hash(user, auth, target) == access_hash

    def to_tl_peer(self) -> PeerUser:
        return PeerUser(user_id=self.id)

    @classmethod
    async def get_from_input(
            cls, user_id: int, target_id: InputPeerSelf | InputPeerUser | InputUserSelf | InputUser,
            select_related: tuple[str, ...] = (),
    ) -> Self | None:
        if isinstance(target_id, (InputPeerSelf, InputUserSelf)) \
                or (isinstance(target_id, (InputPeerUser, InputUser)) and target_id.user_id == user_id):
            return await cls.get(id=user_id).select_related(*select_related)
        elif isinstance(target_id, (InputPeerUser, InputUser)):
            ctx = request_ctx.get()
            if not cls.check_access_hash(user_id, ctx.auth_id, target_id.user_id, target_id.access_hash):
                return None
            return await cls.get_or_none(id=target_id.user_id).select_related(*select_related)

    @classmethod
    async def get_from_input_raise(
            cls, user_id: int, target_id: InputPeerSelf | InputPeerUser | InputUserSelf | InputUser,
            select_related: tuple[str, ...] = (), code: int = 400, message: str = "PEER_ID_INVALID",
    ) -> Self:
        user = await cls.get_from_input(user_id, target_id, select_related)
        if user is not None:
            return user
        raise ErrorRpc(error_code=code, error_message=message)

    async def inc_version(self) -> None:
        await User.filter(id=self.id).update(version=F("version") + 1)
        await self.refresh_from_db(["version"])

    @classmethod
    async def add_pts(cls, user: models.User | int, pts_count: int) -> int:
        user_id = user.id if isinstance(user, models.User) else user

        if pts_count <= 0:
            return cast(int, await cls.get(id=user_id).values_list("pts", flat=True))

        async with in_transaction():
            pts = cast(int, await cls.select_for_update().get(id=user_id).values_list("pts", flat=True))
            new_pts = pts + pts_count
            await cls.filter(id=user_id).update(pts=new_pts)

        return new_pts

    @classmethod
    async def add_pts_bulk(cls, users: list[models.User | int], pts_counts: Collection[int] | int) -> list[int]:
        if not users:
            return []

        user_ids = [(user.id if isinstance(user, models.User) else user) for user in users]

        if not isinstance(pts_counts, Collection):
            pts_counts = SingleElementList(pts_counts, len(users))
        if len(pts_counts) != len(users):
            raise ValueError("\"users\" and \"pts_count\" must have same length")

        async with in_transaction():
            to_update = []
            user_by_user_id = {
                user.id: user
                for user in await cls.select_for_update().filter(id__in=user_ids).only("id", "pts")
            }

            for user_id, pts_count in zip(user_ids, pts_counts):
                if pts_count <= 0:
                    continue
                state = user_by_user_id[user_id]
                state.pts += pts_count
                to_update.append(state)

            if to_update:
                await cls.bulk_update(to_update, fields=["pts"])

        return [user_by_user_id[user_id].pts for user_id in user_ids]

    async def update_presence_to_now(self) -> None:
        if self.bot:
            raise RuntimeError("Can't set presence for bot")

        self.last_seen = datetime.now(UTC)
        await self.save(update_fields=["last_seen"])

    async def to_tl_presence(
            self, user: models.User | int | None, has_access: bool | Missing = MISSING,
    ) -> TLUserStatusBase:
        now = datetime.now(UTC)
        delta = now - self.last_seen
        if delta < timedelta(seconds=30):
            return UserStatusOnline(expires=int(time() + 30))

        if has_access is _MISSING:
            if user is None:
                has_access = False
            else:
                user_id = user.id if isinstance(user, models.User) else user
                has_access = await models.PrivacyRule.has_access_to(
                    user_id, self.id, PrivacyRuleKeyType.STATUS_TIMESTAMP
                )

        return self.to_tl_presence_noprivacycheck(has_access)

    def to_tl_presence_noprivacycheck(self, has_access: bool) -> TLUserStatusBase:
        return self.to_tl_presence_from_last_seen(int(self.last_seen.timestamp()), has_access)

    @classmethod
    def to_tl_presence_from_last_seen(cls, last_seen: int, has_access: bool) -> TLUserStatusBase:
        now = datetime.now(UTC)
        delta = now - datetime.fromtimestamp(last_seen, UTC)
        if delta < timedelta(seconds=30):
            return UserStatusOnline(expires=int(time() + 30))

        if has_access:
            return UserStatusOffline(was_online=last_seen)

        if delta <= timedelta(days=3):
            return STATUS_RECENTLY
        if delta <= timedelta(days=7):
            return STATUS_LAST_WEEK
        if delta <= timedelta(days=28):
            return STATUS_LAST_MONTH

        return STATUS_EMPTY
