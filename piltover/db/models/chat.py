from __future__ import annotations

from tortoise import fields
from tortoise.functions import Count

from piltover.db import models
from piltover.db.enums import PeerType
from piltover.db.models.chat_base import ChatBase
from piltover.tl import ChatForbidden
from piltover.tl.types import Chat as TLChat, ChatAdminRights, InputChannel

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
    # TODO: store participants count in model field
    migrated: bool = fields.BooleanField(default=False)

    def make_id(self) -> int:
        return self.make_id_from(self.id)

    @classmethod
    def make_id_from(cls, in_id: int) -> int:
        return in_id * 2

    def _to_tl(
            self, user_id: int, participant: models.ChatParticipant, participants_count: int, photo: models.File | None,
            migrated_to: InputChannel | None,
    ) -> TLChat:
        return TLChat(
            creator=self.creator_id == user_id,
            left=False,
            deactivated=self.migrated,
            call_active=False,
            call_not_empty=False,
            noforwards=self.no_forwards,
            id=self.make_id(),
            title=self.name,
            photo=self.to_tl_chat_photo_internal(photo),
            participants_count=participants_count,
            date=int(self.created_at.timestamp()),
            version=self.version,
            migrated_to=migrated_to,
            admin_rights=DEFAULT_ADMIN_RIGHTS if participant.is_admin or self.creator_id == user_id else None,
            default_banned_rights=self.banned_rights.to_tl(),
        )

    async def to_tl(self, user: models.User) -> TLChat | ChatForbidden:
        participant = await models.ChatParticipant.get_or_none(user=user, chat=self)
        if participant is None:
            return ChatForbidden(id=self.make_id(), title=self.name)

        migrated_to = None
        if self.migrated and (to_channel := await models.Channel.get_or_none(migrated_from=self)) is not None:
            await models.Peer.get_or_create(owner=user, type=PeerType.CHANNEL, channel=to_channel)
            migrated_to = InputChannel(channel_id=to_channel.make_id(), access_hash=-1)

        if self.photo is not None:
            self.photo = await self.photo

        return self._to_tl(
            user.id, participant, await models.ChatParticipant.filter(chat=self).count(), self.photo, migrated_to,
        )

    @classmethod
    async def to_tl_bulk(cls, chats: list[models.Chat], user: models.User) -> list[TLChat | ChatForbidden]:
        if not chats:
            return []

        chat_ids = [chat.id for chat in chats]

        participants = {
            participant.chat_id: participant
            for participant in await models.ChatParticipant.filter(user=user, chat__id__in=chat_ids)
        }

        migrated_tos = {
            channel.migrated_from_id: channel
            for channel in await models.Channel.filter(migrated_from__id__in=chat_ids)
        }

        chat_by_photo = {
            chat.photo_id: chat.id
            for chat in chats
            if chat.photo_id is not None and not isinstance(chat.photo, models.File)
        }
        photos = {
            chat_by_photo[photo.id]: photo
            for photo in await models.File.filter(id__in=list(chat_by_photo))
        }
        for chat in chats:
            if chat.photo_id is not None and isinstance(chat.photo, models.File):
                photos[chat.id] = chat.photo

        participant_counts = {
            chat_id: count
            for chat_id, count in await models.ChatParticipant.filter(
                chat__id__in=chat_ids,
            ).group_by("chat__id").annotate(participants=Count("id")).values_list("chat__id", "participants")
        }

        tl = []
        for chat in chats:
            participant = participants.get(chat.id)
            if participant is None:
                tl.append(ChatForbidden(id=chat.make_id(), title=chat.name))
                continue

            migrated_to = None
            if chat.migrated and chat.id in migrated_tos:
                migrated_to = InputChannel(channel_id=migrated_tos[chat.id].make_id(), access_hash=-1)

            tl.append(chat._to_tl(
                user.id, participant, participant_counts[chat.id], photos.get(chat.id), migrated_to,
            ))

        return tl

