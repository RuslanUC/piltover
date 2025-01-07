from __future__ import annotations

from datetime import date

from tortoise import fields, Model

from piltover.db import models
from piltover.db.enums import PeerType
from piltover.tl import UserProfilePhotoEmpty, UserProfilePhoto, PhotoEmpty, Birthday
from piltover.tl.types import User as TLUser


class User(Model):
    id: int = fields.BigIntField(pk=True)
    phone_number: str = fields.CharField(unique=True, max_length=20)
    first_name: str = fields.CharField(max_length=128)
    last_name: str | None = fields.CharField(max_length=128, null=True, default=None)
    username: str | None = fields.CharField(max_length=64, null=True, default=None, index=True)
    lang_code: str = fields.CharField(max_length=8, default="en")
    about: str | None = fields.CharField(max_length=240, null=True, default=None)
    ttl_days: int = fields.IntField(default=365)
    birthday: date | None = fields.DateField(null=True, default=None)

    async def get_photo(self, current_user: models.User, profile_photo: bool = False):
        photo = UserProfilePhotoEmpty() if profile_photo else PhotoEmpty(id=0)
        if await models.UserPhoto.filter(user=self).exists():
            photo = (await models.UserPhoto.get_or_none(user=self, current=True).select_related("file") or
                     await models.UserPhoto.filter(user=self).select_related("file").order_by("-id").first())

            if profile_photo:
                stripped: str | None = photo.file.attributes.get("_size_stripped", None)
                stripped = bytes.fromhex(stripped) if stripped is not None else None
                photo = UserProfilePhoto(has_video=False, photo_id=photo.id, dc_id=2, stripped_thumb=stripped)
            else:
                photo = await photo.to_tl(current_user)

        return photo

    async def to_tl(self, current_user: models.User | None = None, **kwargs) -> TLUser:
        # TODO: add some "version" field and save tl user in some cache with key f"{self.id}:{current_user.id}:{version}"

        defaults = {
                       "mutual_contact": False,
                       "deleted": False,
                       "bot": False,
                       "verified": True,
                       "restricted": False,
                       "min": False,
                       "support": False,
                       "scam": False,
                       "apply_min_photo": False,
                       "fake": False,
                       "bot_attach_menu": False,
                       "premium": False,
                       "attach_menu_enabled": False,
                   } | kwargs

        peer = await models.Peer.get_or_none(owner=current_user, user__id=self.id, type=PeerType.USER)
        contact = await models.Contact.get_or_none(owner=current_user, target=self)

        return TLUser(
            **defaults,
            id=self.id,
            first_name=self.first_name if contact is None or not contact.first_name else contact.first_name,
            last_name=self.last_name if contact is None or not contact.last_name else contact.last_name,
            username=self.username,
            phone=self.phone_number,
            lang_code=self.lang_code,
            is_self=self == current_user,
            photo=await self.get_photo(current_user, True),
            access_hash=peer.access_hash if peer is not None else 1,
            status=await models.Presence.to_tl_or_empty(self, current_user),
            contact=contact is not None,
        )

    @classmethod
    async def from_ids(cls, ids: list[int] | set[int]) -> list[models.User]:
        result = []
        for uid in ids:
            if (user := await User.get_or_none(id=uid)) is not None:
                result.append(user)
        return result

    def to_tl_birthday(self) -> Birthday | None:
        if self.birthday is None:
            return

        return Birthday(
            day=self.birthday.day,
            month=self.birthday.month,
            year=self.birthday.year if self.birthday.year != 1900 else None,
        )
