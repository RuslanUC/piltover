from __future__ import annotations

from tortoise import fields

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
    migrated: bool = fields.BooleanField(default=False)

    def make_id(self) -> int:
        return self.make_id_from(self.id)

    @classmethod
    def make_id_from(cls, in_id: int) -> int:
        return in_id * 2

    async def to_tl(self, user: models.User) -> TLChat | ChatForbidden:
        participant = await models.ChatParticipant.get_or_none(user=user, chat=self)
        if participant is None:
            return ChatForbidden(id=self.make_id(), title=self.name)

        migrated_to = None
        if self.migrated and (to_channel := await models.Channel.get_or_none(migrated_from=self)) is not None:
            peer, _ = await models.Peer.get_or_create(owner=user, type=PeerType.CHANNEL, channel=to_channel)
            migrated_to = InputChannel(channel_id=to_channel.make_id(), access_hash=peer.access_hash)

        return TLChat(
            creator=self.creator_id == user.id,
            left=False,
            deactivated=self.migrated,
            call_active=False,
            call_not_empty=False,
            noforwards=self.no_forwards,
            id=self.make_id(),
            title=self.name,
            photo=await self.to_tl_chat_photo(),
            participants_count=await models.ChatParticipant.filter(chat=self).count(),
            date=int(self.created_at.timestamp()),
            version=self.version,
            migrated_to=migrated_to,
            admin_rights=DEFAULT_ADMIN_RIGHTS if participant.is_admin or self.creator_id == user.id else None,
            default_banned_rights=self.banned_rights.to_tl(),
        )
