from __future__ import annotations

from piltover.db import models
from piltover.db.models.chat_base import ChatBase
from piltover.tl import ChatForbidden
from piltover.tl.types import Chat as TLChat, ChatAdminRights

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
    async def to_tl(self, user: models.User) -> TLChat | ChatForbidden:
        participant = await models.ChatParticipant.get_or_none(user=user, chat=self)
        if participant is None:
            return ChatForbidden(id=self.id, title=self.name)

        return TLChat(
            creator=self.creator_id == user.id,
            left=False,
            deactivated=False,
            call_active=False,
            call_not_empty=False,
            noforwards=self.no_forwards,
            id=self.id,
            title=self.name,
            photo=await self.to_tl_chat_photo(),
            participants_count=await models.ChatParticipant.filter(chat=self).count(),
            date=int(self.created_at.timestamp()),
            version=self.version,
            migrated_to=None,
            admin_rights=DEFAULT_ADMIN_RIGHTS if participant.is_admin or self.creator_id == user.id else None,
            default_banned_rights=self.banned_rights.to_tl(),
        )
