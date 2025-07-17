from __future__ import annotations

from datetime import date

from tortoise import fields, Model

from piltover.db import models
from piltover.db.enums import PeerType, PrivacyRuleKeyType
from piltover.tl import UserProfilePhotoEmpty, UserProfilePhoto, PhotoEmpty, Birthday
from piltover.tl.types import User as TLUser

_USERNAME_MISSING = object()

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
    default_reaction: models.Reaction = fields.ForeignKeyField("models.Reaction", null=True, default=None)

    default_reaction_id: int | None

    cached_username: models.Username | None | object = _USERNAME_MISSING
    is_lazy: bool = False

    async def load_if_lazy(self) -> None:
        if not self.is_lazy:
            return

        obj = await self.get(id=self.id)
        for field in self._meta.db_fields:
            setattr(self, field, getattr(obj, field, None))

        self._saved_in_db = True
        self.is_lazy = False

    async def get_username(self) -> models.Username | None:
        if self.cached_username is _USERNAME_MISSING:
            self.cached_username = await models.Username.get_or_none(user=self)

        return self.cached_username

    async def get_raw_username(self) -> str | None:
        username = await self.get_username()
        if username is not None:
            return username.username

    async def get_photo(self, current_user: models.User, profile_photo: bool = False):
        photo = UserProfilePhotoEmpty() if profile_photo else PhotoEmpty(id=0)
        if not await models.PrivacyRule.has_access_to(current_user, self, PrivacyRuleKeyType.PROFILE_PHOTO):
            return photo
        if not await models.UserPhoto.filter(user=self).exists():
            return photo

        photo = (await models.UserPhoto.get_or_none(user=self, current=True).select_related("file") or
                 await models.UserPhoto.filter(user=self).select_related("file").order_by("-id").first())

        if profile_photo:
            photo = UserProfilePhoto(
                has_video=False, photo_id=photo.id, dc_id=2, stripped_thumb=photo.file.photo_stripped,
            )
        else:
            photo = await photo.to_tl(current_user)

        return photo

    async def to_tl(self, current_user: models.User | None = None) -> TLUser:
        # TODO: min (https://core.telegram.org/api/min)
        # TODO: add some "version" field and save tl user in some cache with key f"{self.id}:{current_user.id}:{version}"

        defaults = {
            "mutual_contact": False,
            "deleted": False,
            "verified": False,
            "restricted": False,
            "min": False,
            "support": False,
            "scam": False,
            "apply_min_photo": False,
            "fake": False,
            "bot_attach_menu": False,
            "premium": False,
            "attach_menu_enabled": False,
        }

        peer = await models.Peer.get_or_none(owner=current_user, user__id=self.id, type=PeerType.USER)
        contact = await models.Contact.get_or_none(owner=current_user, target=self)

        phone_number = None
        if await models.PrivacyRule.has_access_to(current_user, self, PrivacyRuleKeyType.PHONE_NUMBER):
            phone_number = self.phone_number

        username = await self.get_username()

        return TLUser(
            **defaults,
            id=self.id,
            first_name=self.first_name if contact is None or not contact.first_name else contact.first_name,
            last_name=self.last_name if contact is None or not contact.last_name else contact.last_name,
            username=username.username if username is not None else None,
            phone=phone_number,
            lang_code=self.lang_code,
            is_self=self == current_user,
            photo=await self.get_photo(current_user, True),
            access_hash=peer.access_hash if peer is not None else 1,
            status=await models.Presence.to_tl_or_empty(self, current_user),
            contact=contact is not None,
            bot=self.bot,
            bot_info_version=1 if self.bot else None,
        )

    async def to_tl_birthday(self, user: User) -> Birthday | None:
        if self.birthday is None or not await models.PrivacyRule.has_access_to(user, self, PrivacyRuleKeyType.BIRTHDAY):
            return None

        return Birthday(
            day=self.birthday.day,
            month=self.birthday.month,
            year=self.birthday.year if self.birthday.year != 1900 else None,
        )
