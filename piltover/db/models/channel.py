from __future__ import annotations

from time import time
from typing import cast

from tortoise import fields

from piltover.db import models
from piltover.db.enums import PeerType
from piltover.db.models import ChatBase
from piltover.tl import ChannelForbidden, Channel as TLChannel
from piltover.tl.types import ChatAdminRights


ADMIN_RIGHTS = ChatAdminRights(
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


class Channel(ChatBase):
    channel: bool = fields.BooleanField(default=False)
    supergroup: bool = fields.BooleanField(default=False)
    pts: int = fields.BigIntField(default=1)

    async def to_tl(self, user: models.User) -> TLChannel | ChannelForbidden:
        peer: models.Peer | None = await models.Peer.get_or_none(owner=user, channel=self, type=PeerType.CHANNEL)
        if peer is None or (participant := await models.ChatParticipant.get_or_none(user=user, channel=self)) is None:
            return ChannelForbidden(
                id=self.id,
                access_hash=0 if peer is None else cast(models.Peer, peer).access_hash,
                title=self.name,
            )

        return TLChannel(
            id=self.id,
            title=self.name,
            photo=await self.to_tl_chat_photo(),
            date=int(time()),
            creator=self.creator == user,
            left=False,
            broadcast=self.channel,
            verified=False,
            megagroup=self.supergroup,
            restricted=False,
            signatures=False,
            min=False,
            scam=False,
            has_link=False,
            has_geo=False,
            slowmode_enabled=False,
            call_active=False,
            call_not_empty=False,
            fake=False,
            gigagroup=False,
            noforwards=False,
            join_to_send=True,
            join_request=False,
            forum=False,
            stories_hidden=False,
            stories_hidden_min=True,
            stories_unavailable=True,
            access_hash=peer.access_hash,
            restriction_reason=None,
            admin_rights=ADMIN_RIGHTS if participant.is_admin or self.creator_id == user.id else None,
            usernames=[],
        )
