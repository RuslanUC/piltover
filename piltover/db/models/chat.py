from __future__ import annotations

from time import time

from piltover.db import models
from piltover.db.models.chat_base import ChatBase
from piltover.tl import ChatForbidden
from piltover.tl.types import Chat as TLChat, ChatBannedRights, ChatAdminRights

DEFAULT_BANNED_RIGHTS = ChatBannedRights(
    view_messages=False,
    send_messages=False,
    send_media=False,
    send_stickers=False,
    send_gifs=False,
    send_games=False,
    send_inline=False,
    embed_links=False,
    send_polls=False,
    change_info=False,
    invite_users=False,
    pin_messages=False,
    manage_topics=False,
    send_photos=False,
    send_videos=False,
    send_roundvideos=False,
    send_audios=False,
    send_voices=False,
    send_docs=False,
    send_plain=False,
    until_date=2147483647,
)
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
            date=int(time()),  # ??
            version=self.version,
            migrated_to=None,
            admin_rights=DEFAULT_ADMIN_RIGHTS if participant.is_admin or self.creator_id == user.id else None,
            default_banned_rights=DEFAULT_BANNED_RIGHTS,
        )
