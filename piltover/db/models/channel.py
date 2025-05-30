from __future__ import annotations

from typing import cast

from tortoise import fields
from tortoise.expressions import Q

from piltover.db import models
from piltover.db.enums import PeerType
from piltover.db.models import ChatBase
from piltover.tl import ChannelForbidden, Channel as TLChannel
from piltover.tl.types import ChatAdminRights

CREATOR_RIGHTS = ChatAdminRights(
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
    other=True,
    manage_topics=True,
    post_stories=True,
    edit_stories=True,
    delete_stories=True,
)
_USERNAME_MISSING = object()


class Channel(ChatBase):
    channel: bool = fields.BooleanField(default=False)
    supergroup: bool = fields.BooleanField(default=False)
    pts: int = fields.BigIntField(default=1)
    signatures: bool = fields.BooleanField(default=False)

    cached_username: models.Username | None | object = _USERNAME_MISSING

    async def get_username(self) -> models.Username | None:
        if self.cached_username is _USERNAME_MISSING:
            self.cached_username = await models.Username.get_or_none(channel=self)

        return self.cached_username

    async def to_tl(self, user: models.User | int) -> TLChannel | ChannelForbidden:
        user_id = user.id if isinstance(user, models.User) else user

        peer: models.Peer | None = await models.Peer.get_or_none(owner__id=user_id, channel=self, type=PeerType.CHANNEL)
        if peer is None or (participant := await models.ChatParticipant.get_or_none(user__id=user_id, channel=self)) is None:
            return ChannelForbidden(
                id=self.id,
                access_hash=0 if peer is None else cast(models.Peer, peer).access_hash,
                title=self.name,
            )

        admin_rights = None
        if self.creator_id == user_id:
            admin_rights = CREATOR_RIGHTS
        elif participant.is_admin:
            admin_rights = participant.admin_rights.to_tl()

        username = await self.get_username()

        return TLChannel(
            id=self.id,
            title=self.name,
            photo=await self.to_tl_chat_photo(),
            date=int((participant.invited_at if participant else self.created_at).timestamp()),
            creator=self.creator_id == user_id,
            left=False,
            broadcast=self.channel,
            verified=False,
            megagroup=self.supergroup,
            restricted=False,
            signatures=self.signatures,
            min=False,
            scam=False,
            has_link=False,
            has_geo=False,
            slowmode_enabled=False,
            call_active=False,
            call_not_empty=False,
            fake=False,
            gigagroup=False,
            noforwards=self.no_forwards,
            join_to_send=True,
            join_request=False,
            forum=False,
            stories_hidden=False,
            stories_hidden_min=True,
            stories_unavailable=True,
            access_hash=peer.access_hash,
            restriction_reason=None,
            admin_rights=admin_rights,
            username=username.username if username is not None else None,
            usernames=[],
            default_banned_rights=self.banned_rights.to_tl(),
            banned_rights=participant.banned_rights.to_tl()
        )
