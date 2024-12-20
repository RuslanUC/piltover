from __future__ import annotations

from tortoise import fields

from piltover.context import request_ctx
from piltover.db import models
from piltover.db.models._utils import Model
from piltover.exceptions import ErrorRpc
from piltover.tl import UserProfilePhotoEmpty, UserProfilePhoto, PhotoEmpty, InputUser, InputUserSelf, \
    InputPeerUser, InputPeerSelf
from piltover.tl.types.user import User as TLUser
from piltover.tl.types.user_148 import User_148 as TLUser_148


class User(Model):
    id: int = fields.BigIntField(pk=True)
    phone_number: str = fields.CharField(unique=True, max_length=20)
    first_name: str = fields.CharField(max_length=128)
    last_name: str | None = fields.CharField(max_length=128, null=True, default=None)
    username: str | None = fields.CharField(max_length=64, null=True, default=None, index=True)
    lang_code: str = fields.CharField(max_length=8, default="en")
    about: str | None = fields.CharField(max_length=240, null=True, default=None)
    ttl_days: int = fields.IntField(default=365)

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

    async def to_tl(self, current_user: models.User | None = None, **kwargs) -> TLUser | TLUser_148:
        # TODO: add some "version" field and save tl user in some cache with key f"{self.id}:{current_user.id}:{version}"

        defaults = {
                       "contact": False,
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

        user = TLUser(
            **defaults,
            id=self.id,
            first_name=self.first_name,
            last_name=self.last_name,
            username=self.username,
            phone=self.phone_number,
            lang_code=self.lang_code,
            is_self=self == current_user,
            photo=await self.get_photo(current_user, True),
            access_hash=123456789,  # TODO: make table with access hashes for users
        )

        layer = request_ctx.get().client.layer
        if 160 > layer >= 148:
            user = TLUser_148(
                is_self=user.is_self,
                contact=user.contact,
                mutual_contact=user.mutual_contact,
                deleted=user.deleted,
                bot=user.bot,
                bot_chat_history=user.bot_chat_history,
                bot_nochats=user.bot_nochats,
                verified=user.verified,
                restricted=user.restricted,
                min=user.min,
                bot_inline_geo=user.bot_inline_geo,
                support=user.support,
                scam=user.scam,
                apply_min_photo=user.apply_min_photo,
                fake=user.fake,
                bot_attach_menu=user.bot_attach_menu,
                premium=user.premium,
                attach_menu_enabled=user.attach_menu_enabled,
                bot_can_edit=user.bot_can_edit,
                id=user.id,
                access_hash=user.access_hash,
                first_name=user.first_name,
                last_name=user.last_name,
                username=user.username,
                phone=user.phone,
                photo=user.photo,
                status=user.status,
                bot_info_version=user.bot_info_version,
                restriction_reason=user.restriction_reason,
                bot_inline_placeholder=user.bot_inline_placeholder,
                lang_code=user.lang_code,
                emoji_status=user.emoji_status,
                usernames=user.usernames,
            )

        return user

    @classmethod
    async def from_input_peer(cls, peer, current_user: models.User) -> models.User | None:
        if isinstance(peer, (InputUserSelf, InputPeerSelf)):
            return current_user
        elif isinstance(peer, (InputUser, InputPeerUser)):
            if peer.user_id == current_user.id:
                return current_user
            elif (user := await User.get_or_none(id=peer.user_id)) is None:
                raise ErrorRpc(error_code=400, error_message="PEER_ID_INVALID")
            return user
        else:
            return None

    @classmethod
    async def from_ids(cls, ids: list[int] | set[int]) -> list[models.User]:
        result = []
        for uid in ids:
            if (user := await User.get_or_none(id=uid)) is not None:
                result.append(user)
        return result
