from __future__ import annotations

from tortoise import fields

from piltover.cache import Cache
from piltover.db import models
from piltover.db.models.chat_base import ChatBase
from piltover.tl import ChatForbidden
from piltover.tl.base import Chat as TLChatBase
from piltover.tl.to_format import ChatToFormat
from piltover.tl.types import Chat as TLChat, ChatAdminRights, PeerChat

DEFAULT_ADMIN_RIGHTS = ChatAdminRights(
    change_info=True,
    post_messages=True,
    edit_messages=True,
    delete_messages=True,
    ban_users=True,
    invite_users=True,
    pin_messages=True,
    add_admins=True,
    anonymous=True,
    manage_call=True,
    other=False,
    manage_topics=True,
    post_stories=True,
    edit_stories=True,
    delete_stories=True,
)


class Chat(ChatBase):
    migrated: bool = fields.BooleanField(default=False)
    # TODO: maybe sync this value once in a while
    participants_count: int = fields.SmallIntField()

    def make_id(self) -> int:
        return self.make_id_from(self.id)

    @classmethod
    def make_id_from(cls, in_id: int) -> int:
        return in_id * 2

    def _to_tl(self, photo: models.File | None, migrated_to_id: int | None) -> TLChatBase:
        return ChatToFormat(
            creator_id=self.creator_id,
            deactivated=self.migrated,
            noforwards=self.no_forwards,
            id=self.id,
            title=self.name,
            photo=self.to_tl_chat_photo_internal(photo),
            participants_count=self.participants_count,
            date=int(self.created_at.timestamp()),
            version=self.version,
            migrated_to=migrated_to_id,
            default_banned_rights=self.banned_rights.to_tl(),
        )

    def cache_key(self) -> str:
        return f"chat:{self.id}:{self.version}"

    async def to_tl(self) -> TLChatBase:
        if (cached := await Cache.obj.get(self.cache_key())) is not None:
            return cached

        migrated_to_id = None
        if self.migrated:
            migrated_to_id = await models.Channel.get_or_none(migrated_from=self).values_list("id", flat=True)

        if self.photo is not None:
            self.photo = await self.photo

        result = self._to_tl(self.photo, migrated_to_id)
        await Cache.obj.set(self.cache_key(), result)

        return result

    @classmethod
    async def to_tl_bulk(cls, chats: list[models.Chat]) -> list[TLChat | ChatForbidden]:
        if not chats:
            return []

        cached_chats = await Cache.obj.multi_get([
            chat.cache_key()
            for chat in chats
        ])

        processing_chats = [
            chat
            for chat, cached in zip(chats, cached_chats)
            if cached is None
        ]
        chat_ids = [chat.id for chat in processing_chats]

        migrated_ids = [chat.id for chat in processing_chats if chat.migrated]
        if migrated_ids:
            migrated_tos = {
                migrated_from: migrated_to
                for migrated_from, migrated_to in await models.Channel.filter(
                    migrated_from_id__in=chat_ids,
                ).values_list("migrated_from_id", "id")
            }
        else:
            migrated_tos = {}

        chat_by_photo = {
            chat.photo_id: chat.id
            for chat in processing_chats
            if chat.photo_id is not None and not isinstance(chat.photo, models.File)
        }
        if chat_by_photo:
            photos = {
                chat_by_photo[photo.id]: photo
                for photo in await models.File.filter(id__in=list(chat_by_photo))
            }
        else:
            photos = {}
        for chat in processing_chats:
            if chat.photo_id is not None and isinstance(chat.photo, models.File):
                photos[chat.id] = chat.photo

        tl = []
        to_cache = []
        for chat, cached in zip(chats, cached_chats):
            if cached is not None:
                tl.append(cached)
                continue

            tl.append(chat._to_tl(photos.get(chat.id), migrated_tos.get(chat.id, None)))
            to_cache.append((chat.cache_key(), tl[-1]))

        if to_cache:
            await Cache.obj.multi_set(to_cache)

        return tl

    def to_tl_peer(self) -> PeerChat:
        return PeerChat(chat_id=self.make_id())
