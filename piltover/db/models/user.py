from __future__ import annotations

import hashlib
import hmac
from datetime import date
from enum import auto, Enum
from typing import Iterable, Self

from tortoise import fields, Model
from tortoise.expressions import Q

from piltover.app_config import AppConfig
from piltover.cache import Cache
from piltover.context import request_ctx
from piltover.db import models
from piltover.db.enums import PrivacyRuleKeyType
from piltover.exceptions import Unreachable, ErrorRpc
from piltover.tl import UserProfilePhotoEmpty, PhotoEmpty, Birthday, Long, InputUser
from piltover.tl.to_format import UserToFormat
from piltover.tl.types import User as TLUser, PeerColor, PeerUser, InputPeerSelf, InputPeerUser, InputUserSelf
from piltover.tl.base import User as TLUserBase
from piltover.tl.types.internal_access import AccessHashPayloadUser


class _Missing(Enum):
    MISSING = auto()


_MISSING = _Missing.MISSING
_PROFILE_PHOTO_EMPTY = UserProfilePhotoEmpty()
_PHOTO_EMPTY = PhotoEmpty(id=0)


class User(Model):
    id: int = fields.BigIntField(pk=True)
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

    accent_color_id: int | None
    profile_color_id: int | None

    cached_username: models.Username | None | _Missing = _MISSING

    _CACHE_VERSION = 1

    def _cache_key(self) -> str:
        return f"user:{self.id}:{self.version}:{self._CACHE_VERSION}"

    async def get_username(self) -> models.Username | None:
        if self.cached_username is _MISSING:
            self.cached_username = await models.Username.get_or_none(user=self)

        return self.cached_username

    async def get_raw_username(self) -> str | None:
        username = await self.get_username()
        if username is not None:
            return username.username

    async def get_db_current_photo(self) -> models.UserPhoto | None:
        return await models.UserPhoto.get_or_none(user=self, current=True).select_related("file")

    async def get_db_photos(self) -> tuple[models.UserPhoto | None, models.UserPhoto | None]:
        # TODO: also fetch personal_photo (when will be implemented)

        current = None
        fallback = None

        photos = await models.UserPhoto.filter(
            Q(current=True, fallback=True, join_type=Q.OR), user=self
        ).select_related("file")
        for photo in photos:
            if photo.current:
                current = photo
            elif photo.fallback:
                fallback = photo
            else:
                raise Unreachable

        return current, fallback

    # TODO: fetch ALL privacy rules (including all exceptions) in to_tl/to_tl_bulk
    #  to not refetch them every time in gateway?

    async def to_tl(self, *, userphoto: models.UserPhoto | None | _Missing = _MISSING) -> TLUserBase:
        if self.deleted:
            return TLUser(
                id=self.id,
                is_self=False,
                access_hash=0,
                deleted=True,
            )

        if (cached := await Cache.obj.get(self._cache_key())) is not None:
            return cached

        # TODO: min (https://core.telegram.org/api/min)
        # TODO: add some "version" field and save tl user
        #  in some cache with key f"{self.id}:{current_user.id}:{version}"

        username = await self.get_username()

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
            # TODO: use fallback photo is userphoto is None?
            photo = userphoto.to_tl_profile()

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
        )

        await Cache.obj.set(self._cache_key(), result)
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
                for emojis in await models.UserBackgroundEmojis.filter(user_id__in=user_ids)
            }
        else:
            background_emojis = {}

        if bot_ids:
            bot_versions = {
                user_id: version
                for user_id, version in await models.BotInfo.filter(
                    user_id__in=bot_ids,
                ).values_list("user_id", "version")
            }
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
            ))

            to_cache.append((user.id, tl[-1]))

        if to_cache:
            await Cache.obj.multi_set(to_cache)

        return tl

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
        digest = hmac.new(AppConfig.HMAC_KEY, to_sign, hashlib.sha256).digest()
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
