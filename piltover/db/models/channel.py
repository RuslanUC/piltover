from __future__ import annotations

import hashlib
import hmac
from enum import auto, Enum
from typing import cast

from tortoise import fields
from tortoise.models import MODEL
from tortoise.transactions import in_transaction

from piltover.app_config import AppConfig
from piltover.db import models
from piltover.db.models import ChatBase
from piltover.db.models.utils import NullableFKSetNull
from piltover.tl import ChannelForbidden, Long
from piltover.tl.base import Chat as TLChatBase
from piltover.tl.to_format import ChannelToFormat
from piltover.tl.types import ChatAdminRights as TLChatAdminRights, PeerColor, PeerChannel
from piltover.tl.types.internal_access import AccessHashPayloadChannel

CREATOR_RIGHTS = TLChatAdminRights(
    change_info=True,
    post_messages=True,
    edit_messages=True,
    delete_messages=True,
    ban_users=True,
    invite_users=True,
    pin_messages=True,
    add_admins=True,
    manage_call=True,
    other=True,
    manage_topics=True,
    post_stories=True,
    edit_stories=True,
    delete_stories=True,
)


class _UsernameMissing(Enum):
    USERNAME_MISSING = auto()


_USERNAME_MISSING = _UsernameMissing.USERNAME_MISSING


def NullableFKSetNullR(to: str, related_name: str, **kwargs) -> fields.ForeignKeyNullableRelation[MODEL]:
    return NullableFKSetNull(to=to, related_name=related_name, **kwargs)


class Channel(ChatBase):
    channel: bool = fields.BooleanField(default=False)
    supergroup: bool = fields.BooleanField(default=False)
    pts: int = fields.BigIntField(default=1)
    signatures: bool = fields.BooleanField(default=False)
    accent_color: models.PeerColorOption | None = NullableFKSetNullR("models.PeerColorOption", "channel_accent")
    profile_color: models.PeerColorOption | None = NullableFKSetNullR("models.PeerColorOption", "channel_profile")
    all_reactions: bool = fields.BooleanField(default=True)
    all_reactions_custom: bool = fields.BooleanField(default=False)
    deleted: bool = fields.BooleanField(default=False)
    nojoin_allow_view: bool = fields.BooleanField(default=False)
    hidden_prehistory: bool = fields.BooleanField(default=False)
    min_available_id: int | None = fields.BigIntField(null=True, default=None)
    min_available_id_force: int | None = fields.BigIntField(null=True, default=None)
    migrated_from: models.Chat | None = fields.OneToOneField("models.Chat", null=True, default=None)
    join_to_send: bool = fields.BooleanField(default=True)
    join_request: bool = fields.BooleanField(default=False)
    discussion: models.Channel | None = fields.ForeignKeyField("models.Channel", null=True, default=None)
    is_discussion: bool = fields.BooleanField(default=False)
    accent_emoji: models.File | None = NullableFKSetNullR("models.File", "channel_accent_emoji")
    profile_emoji: models.File | None = NullableFKSetNullR("models.File", "channel_profile_emoji")
    slowmode_seconds: int | None = fields.IntField(null=True, default=None)
    participants_hidden: bool = fields.BooleanField(default=False)

    accent_color_id: int | None
    profile_color_id: int | None
    migrated_from_id: int | None
    discussion_id: int | None
    accent_emoji_id: int | None
    profile_emoji_id: int | None

    cached_username: models.Username | None | _UsernameMissing = _USERNAME_MISSING

    def make_id(self) -> int:
        return self.make_id_from(self.id)

    @classmethod
    def make_id_from(cls, in_id: int) -> int:
        return in_id * 2 + 1

    async def get_username(self) -> models.Username | None:
        if self.cached_username is _USERNAME_MISSING:
            self.cached_username = await models.Username.get_or_none(channel=self)

        return self.cached_username

    async def to_tl(self) -> TLChatBase:
        return (await self.to_tl_bulk([self]))[0]

    @classmethod
    async def to_tl_bulk(cls, channels: list[models.Channel]) -> list[TLChatBase]:
        if not channels:
            return []

        channel_ids = [channel.id for channel in channels]

        if len(channel_ids) == 1:
            channel_id = channel_ids[0]
            usernames = {
                channel_id: await models.Username.filter(
                    channel_id=channel_id,
                ).first().values_list("username", flat=True)
            }
        else:
            usernames = {
                channel_id: username
                for channel_id, username in await models.Username.filter(
                    channel_id__in=channel_ids,
                ).values_list("channel_id", "username")
            }

        if len(channel_ids) == 1:
            channel = channels[0]
            if channel.photo_id is not None:
                photos = {channel.id: await channel.photo}
            else:
                photos = {}
        else:
            channel_by_photo_id = {
                channel.photo_id: channel.id
                for channel in channels
                if channel.photo_id is not None and not isinstance(channel.photo, models.File)
            }
            photos = {
                channel_by_photo_id[photo.id]: photo
                for photo in await models.File.filter(id__in=list(channel_by_photo_id))
            }
            for channel in channels:
                if channel.photo_id is not None and isinstance(channel.photo, models.File):
                    photos[channel.id] = channel.photo

        tl = []
        for channel in channels:
            if channel.deleted:
                tl.append(ChannelForbidden(
                    id=channel.make_id(),
                    access_hash=-1,
                    title=channel.name,
                ))
                continue

            accent_color = None
            profile_color = None
            if channel.accent_color_id is not None or channel.accent_emoji_id is not None:
                accent_color = PeerColor(color=channel.accent_color_id, background_emoji_id=channel.accent_emoji_id)
            if channel.profile_color_id is not None or channel.profile_emoji_id is not None:
                profile_color = PeerColor(color=channel.profile_color_id, background_emoji_id=channel.profile_emoji_id)

            tl.append(ChannelToFormat(
                id=channel.id,
                title=channel.name,
                photo=Channel.to_tl_chat_photo_internal(photos.get(channel.id)),
                created_at=int(channel.created_at.timestamp()),
                creator_id=channel.creator_id,
                broadcast=channel.channel,
                megagroup=channel.supergroup,
                signatures=channel.signatures,
                has_link=channel.discussion_id is not None or channel.is_discussion,
                slowmode_enabled=channel.slowmode_seconds is not None,
                noforwards=channel.no_forwards,
                join_to_send=channel.supergroup and channel.join_to_send,
                join_request=channel.join_request,
                username=usernames.get(channel.id),
                default_banned_rights=channel.banned_rights.to_tl(),
                color=accent_color,
                profile_color=profile_color,
                nojoin_allow_view=channel.nojoin_allow_view,
                # NOTE: participants_count is not included here since it is present in ChannelFull
            ))

        return tl

    def min_id(self, participant: models.ChatParticipant) -> int | None:
        min_available_id_force = self.min_available_id_force or 0
        if participant is not None:
            return max(min_available_id_force, participant.min_message_id or 0) or None
        return max(min_available_id_force, self.min_available_id or 0) or None

    @staticmethod
    def make_access_hash(user: int, auth: int, channel: int) -> int:
        to_sign = AccessHashPayloadChannel(this_user_id=user, channel_id=channel, auth_id=auth).write()
        digest = hmac.new(AppConfig.HMAC_KEY, to_sign, hashlib.sha256).digest()
        return Long.read_bytes(digest[-8:])

    @staticmethod
    def check_access_hash(user: int, auth: int, channel: int, access_hash: int) -> bool:
        return Channel.make_access_hash(user, auth, channel) == access_hash

    def to_tl_peer(self) -> PeerChannel:
        return PeerChannel(channel_id=self.make_id())

    async def add_pts(self, pts_count: int) -> int:
        async with in_transaction():
            pts = cast(int, await Channel.select_for_update().get(id=self.id).values_list("pts", flat=True))

            if pts_count <= 0:
                self.pts = pts
                return pts

            new_pts = pts + pts_count
            await Channel.filter(id=self.id).update(pts=new_pts)

        self.pts = new_pts
        return new_pts
