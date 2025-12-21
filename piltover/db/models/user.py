from __future__ import annotations

import hashlib
import hmac
from datetime import date
from enum import auto, Enum
from typing import overload, Literal, Sequence

from loguru import logger
from tortoise import fields, Model

from piltover.app_config import AppConfig
from piltover.db import models
from piltover.db.enums import PrivacyRuleKeyType
from piltover.tl import UserProfilePhotoEmpty, UserProfilePhoto, PhotoEmpty, Birthday, Long
from piltover.tl.types import User as TLUser, PeerColor, Photo
from piltover.tl.types.internal_access import AccessHashPayloadUser


class _UsernameMissing(Enum):
    USERNAME_MISSING = auto()


_USERNAME_MISSING = _UsernameMissing.USERNAME_MISSING


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

    accent_color_id: int | None
    profile_color_id: int | None

    cached_username: models.Username | None | _UsernameMissing = _USERNAME_MISSING
    is_lazy: bool = False

    async def get_username(self) -> models.Username | None:
        if self.cached_username is _USERNAME_MISSING:
            self.cached_username = await models.Username.get_or_none(user=self)

        return self.cached_username

    async def get_raw_username(self) -> str | None:
        username = await self.get_username()
        if username is not None:
            return username.username

    @overload
    async def get_photo(
            self, current_user: models.User, profile_photo: Literal[True] = True,
    ) -> UserProfilePhoto | UserProfilePhotoEmpty:
        ...

    @overload
    async def get_photo(
            self, current_user: models.User, profile_photo: Literal[False] = False,
    ) -> Photo | PhotoEmpty:
        ...

    async def get_photo(
            self, current_user: models.User, profile_photo: bool = False,
    ) -> UserProfilePhoto | UserProfilePhotoEmpty | Photo | PhotoEmpty:
        empty = UserProfilePhotoEmpty() if profile_photo else PhotoEmpty(id=0)
        if not await models.PrivacyRule.has_access_to(current_user, self, PrivacyRuleKeyType.PROFILE_PHOTO):
            return empty

        photo = await models.UserPhoto.filter(
            user=self
        ).order_by("current", "-id").select_related("file").first()
        if photo is None:
            return empty

        if profile_photo:
            return UserProfilePhoto(
                has_video=False,
                photo_id=photo.id,
                dc_id=2,
                stripped_thumb=photo.file.photo_stripped,
            )

        return photo.to_tl()

    async def to_tl(self, current_user: models.User, peer: models.Peer | None = None) -> TLUser:
        # TODO: min (https://core.telegram.org/api/min)
        # TODO: add some "version" field and save tl user
        #  in some cache with key f"{self.id}:{current_user.id}:{version}"

        if peer is None:
            peer_exists = await models.Peer.filter(owner=current_user, user__id=self.id).exists()
        else:
            peer_exists = True

        contact = await models.Contact.get_or_none(owner=current_user, target=self)
        is_contact = contact is not None

        phone_number = None
        if await models.PrivacyRule.has_access_to(current_user, self, PrivacyRuleKeyType.PHONE_NUMBER):
            phone_number = self.phone_number

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

        return TLUser(
            id=self.id,
            first_name=self.first_name if contact is None or not contact.first_name else contact.first_name,
            last_name=self.last_name if contact is None or not contact.last_name else contact.last_name,
            username=username.username if username is not None else None,
            phone=phone_number,
            lang_code=self.lang_code,
            is_self=self == current_user,
            photo=await self.get_photo(current_user, True),
            access_hash=-1 if peer_exists else 0,
            status=await models.Presence.to_tl_or_empty(self, current_user),
            contact=is_contact,
            bot=self.bot,
            bot_info_version=bot_info_version,
            color=color,
            profile_color=profile_color,
            deleted=self.deleted,
            mutual_contact=is_contact and await models.Contact.filter(owner=self, target=current_user).exists(),

            verified=False,
            restricted=False,
            min=False,
            support=False,
            scam=False,
            apply_min_photo=False,
            fake=False,
            bot_attach_menu=False,
            # TODO: this is True only because custom emojis are not available (like at all, missing in emoji list)
            #  for non-premium users.
            #  Need to figure out how official telegram allows custom emojis to be visible to non-premium users.
            premium=not self.bot,
            attach_menu_enabled=False,
        )

    @classmethod
    async def to_tl_bulk(cls, users: list[models.User], current: models.User) -> list[TLUser]:
        # TODO: "bottlenecks" are PrivacyRule.has_access_to, User.get_photo and Presence.to_tl_or_empty.
        #  User.get_photo and Presence.to_tl_or_empty both use PrivacyRule.has_access_to,
        #  so it needs to be made bulk-available first.

        if not users:
            return []

        all_ids = [user.id for user in users]
        user_ids = [user.id for user in users if not user.bot]
        bot_ids = [user.id for user in users if user.bot]

        peer_ids = set(await models.Peer.filter(owner=current, user__id__in=all_ids).values_list("user_id", flat=True))

        contacts = {
            contact.target_id: contact
            for contact in await models.Contact.filter(owner=current, target__id__in=user_ids)
        } if user_ids else {}
        mutual_contacts = set(
            await models.Contact.filter(
                owner__id__in=list(contacts), target=current,
            ).values_list("owner__id", flat=True)
        ) if contacts else {}

        usernames = {
            user_id: username
            for user_id, username in await models.Username.filter(
                user__id__in=all_ids,
            ).values_list("user_id", "username")
        }

        background_emojis = {
            emojis.user_id: emojis
            for emojis in await models.UserBackgroundEmojis.filter(user__id__in=user_ids)
        } if user_ids else {}

        bot_versions = {
            user_id: version
            for user_id, version in await models.BotInfo.filter(user__id__in=bot_ids).values_list("user_id", "version")
        } if bot_ids else {}

        presences = {
            presence.user_id: presence
            for presence in await models.Presence.filter(user__id__in=user_ids)
        } if user_ids else {}

        tl = []
        for user in users:
            phone_number = None
            if await models.PrivacyRule.has_access_to(current, user, PrivacyRuleKeyType.PHONE_NUMBER):
                phone_number = user.phone_number

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

            bot_info_version = None
            if user.bot:
                bot_info_version = bot_versions.get(user.id, 1)

            contact = contacts.get(user.id)

            tl.append(TLUser(
                id=user.id,
                first_name=user.first_name if contact is None or not contact.first_name else contact.first_name,
                last_name=user.last_name if contact is None or not contact.last_name else contact.last_name,
                username=usernames.get(user.id),
                phone=phone_number,
                lang_code=user.lang_code,
                is_self=user == current,
                photo=await user.get_photo(current, True),
                access_hash=-1 if user.id in peer_ids else 0,
                status=await models.Presence.to_tl_or_empty(user, current, presences.get(user.id)),
                contact=contact is not None,
                bot=user.bot,
                bot_info_version=bot_info_version,
                color=color,
                profile_color=profile_color,
                deleted=user.deleted,
                mutual_contact=user.id in mutual_contacts,

                verified=False,
                restricted=False,
                min=False,
                support=False,
                scam=False,
                apply_min_photo=False,
                fake=False,
                bot_attach_menu=False,
                # TODO: this is True only because custom emojis are not available (like at all, missing in emoji list)
                #  for non-premium users.
                #  Need to figure out how official telegram allows custom emojis to be visible to non-premium users.
                premium=not user.bot,
                attach_menu_enabled=False,
            ))

        return tl

    async def to_tl_birthday(self, user: User) -> Birthday | None:
        if self.birthday is None or not await models.PrivacyRule.has_access_to(user, self, PrivacyRuleKeyType.BIRTHDAY):
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
