from __future__ import annotations

from datetime import datetime

from tortoise import fields, Model
from tortoise.expressions import Q

from piltover.db import models
from piltover.db.enums import ChatBannedRights
from piltover.db.models._utils import IntFlagField
from piltover.exceptions import ErrorRpc
from piltover.tl import Chat, ChatForbidden, ChannelForbidden, Channel, Photo, PhotoEmpty, ChatPhoto, ChatPhotoEmpty

_PHOTO_MISSING = object()


class ChatBase(Model):
    id: int = fields.BigIntField(pk=True)
    name: str = fields.CharField(max_length=64)
    description: str = fields.CharField(max_length=255, default="")
    version: int = fields.BigIntField(default=1)
    creator: models.User = fields.ForeignKeyField("models.User")
    photo: models.File | None = fields.ForeignKeyField("models.File", on_delete=fields.SET_NULL, null=True, default=None)
    no_forwards: bool = fields.BooleanField(default=False)
    banned_rights: ChatBannedRights = IntFlagField(ChatBannedRights, default=ChatBannedRights(0))
    created_at: datetime = fields.DatetimeField(auto_now_add=True)

    creator_id: int
    photo_id: int

    class Meta:
        abstract = True

    async def update(
            self, title: str | None = None, description: str | None = None,
            photo: models.File | None | object = _PHOTO_MISSING
    ) -> None:
        save_fields = []

        if title is not None:
            title = title.strip()
            if title == self.name:
                raise ErrorRpc(error_code=400, error_message="CHAT_NOT_MODIFIED")
            if not title:
                raise ErrorRpc(error_code=400, error_message="CHAT_TITLE_EMPTY")

            self.name = title
            save_fields.append("name")

        if description is not None:
            description = description.strip()
            if description == self.name:
                raise ErrorRpc(error_code=400, error_message="CHAT_ABOUT_NOT_MODIFIED")
            if len(description) > 255:
                raise ErrorRpc(error_code=400, error_message="CHAT_ABOUT_TOO_LONG")

            self.description = description
            save_fields.append("description")

        if photo is not _PHOTO_MISSING:
            if photo == self.photo:
                raise ErrorRpc(error_code=400, error_message="CHAT_NOT_MODIFIED")

            self.photo = photo
            save_fields.append("photo_id")

        if not save_fields:
            return

        self.version += 1
        await self.save(update_fields=[*save_fields, "version"])

    async def to_tl_photo(self, user: models.User) -> Photo | PhotoEmpty:
        if not self.photo_id:
            return PhotoEmpty(id=0)
        self.photo = await self.photo
        return await self.photo.to_tl_photo(user)

    async def to_tl_chat_photo(self) -> ChatPhoto | ChatPhotoEmpty:
        if not self.photo_id:
            return ChatPhotoEmpty()
        self.photo = await self.photo
        return ChatPhoto(
            has_video=False, photo_id=self.photo.id, dc_id=2, stripped_thumb=self.photo.photo_stripped,
        )

    @staticmethod
    def or_channel(chat_or_channel: ChatBase) -> dict:
        if isinstance(chat_or_channel, models.Chat):
            return {"chat": chat_or_channel}
        if isinstance(chat_or_channel, models.Channel):
            return {"channel": chat_or_channel}

        raise NotImplementedError

    or_chat = or_channel

    @staticmethod
    def query(chat_or_channel: models.ChatBase, prefix_field: str | None = None) -> Q:
        if isinstance(chat_or_channel, models.Chat):
            key = f"{prefix_field}__chat" if prefix_field else "chat"
            return Q(**{key: chat_or_channel})
        if isinstance(chat_or_channel, models.Channel):
            key = f"{prefix_field}__channel" if prefix_field else "channel"
            return Q(**{key: chat_or_channel})

        raise NotImplementedError

    async def get_participant(self, user: models.User) -> models.ChatParticipant | None:
        return await models.ChatParticipant.get_or_none(**self.or_channel(self), user=user)

    async def get_participant_raise(self, user: models.User) -> models.ChatParticipant:
        if (participant := await self.get_participant(user)) is not None:
            return participant
        raise ErrorRpc(error_code=400, error_message="CHAT_RESTRICTED")

    def user_has_permission(self, participant: models.ChatParticipant, permission: ChatBannedRights) -> bool:
        if isinstance(self, models.Channel) \
                and self.channel \
                and not participant.is_admin \
                and self.creator_id != participant.user_id:
            return False

        return participant.is_admin or \
            self.creator_id == participant.user_id \
            or not (participant.banned_rights & permission or self.banned_rights & permission)

    async def to_tl(self, user: models.User) -> Chat | ChatForbidden | Channel | ChannelForbidden:
        raise NotImplemented
