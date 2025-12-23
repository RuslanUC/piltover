from __future__ import annotations

import hashlib
import hmac
from enum import auto, Enum

from tortoise import fields

from piltover.app_config import AppConfig
from piltover.db import models
from piltover.db.enums import PeerType, ChatAdminRights
from piltover.db.models import ChatBase
from piltover.tl import ChannelForbidden, Channel as TLChannel, Long
from piltover.tl.types import ChatAdminRights as TLChatAdminRights, PeerColor
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


class Channel(ChatBase):
    channel: bool = fields.BooleanField(default=False)
    supergroup: bool = fields.BooleanField(default=False)
    pts: int = fields.BigIntField(default=1)
    signatures: bool = fields.BooleanField(default=False)
    accent_color: models.PeerColorOption | None = fields.ForeignKeyField("models.PeerColorOption", null=True, default=None, related_name="channel_accent")
    profile_color: models.PeerColorOption | None = fields.ForeignKeyField("models.PeerColorOption", null=True, default=None, related_name="channel_profile")
    all_reactions: bool = fields.BooleanField(default=True)
    all_reactions_custom: bool = fields.BooleanField(default=False)
    deleted: bool = fields.BooleanField(default=False)
    nojoin_allow_view: bool = fields.BooleanField(default=False)
    hidden_prehistory: bool = fields.BooleanField(default=False)
    min_available_id: int | None = fields.BigIntField(null=True, default=None)
    migrated_from: models.Chat | None = fields.OneToOneField("models.Chat", null=True, default=None)
    join_to_send: bool = fields.BooleanField(default=True)
    join_request: bool = fields.BooleanField(default=False)
    discussion: models.Channel | None = fields.ForeignKeyField("models.Channel", null=True, default=None)
    is_discussion: bool = fields.BooleanField(default=False)

    accent_color_id: int | None
    profile_color_id: int | None
    migrated_from_id: int | None
    discussion_id: int | None

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

    def _to_tl(
            self, user_id: int, participant: models.ChatParticipant | None, photo: models.File | None,
            username: str | None,
    ) -> TLChannel:
        admin_rights = None
        if self.creator_id == user_id:
            admin_rights = CREATOR_RIGHTS
            if participant is not None \
                    and participant.admin_rights & ChatAdminRights.ANONYMOUS == ChatAdminRights.ANONYMOUS:
                admin_rights.anonymous = True
        elif participant is not None and participant.is_admin:
            admin_rights = participant.admin_rights.to_tl()

        return TLChannel(
            id=self.make_id(),
            title=self.name,
            photo=self.to_tl_chat_photo_internal(photo),
            date=int((participant.invited_at if participant else self.created_at).timestamp()),
            creator=self.creator_id == user_id,
            left=participant is None,
            broadcast=self.channel,
            verified=False,
            megagroup=self.supergroup,
            restricted=False,
            signatures=self.signatures,
            min=False,
            scam=False,
            has_link=self.discussion_id is not None or self.is_discussion,
            has_geo=False,
            slowmode_enabled=False,
            call_active=False,
            call_not_empty=False,
            fake=False,
            gigagroup=False,
            noforwards=self.no_forwards,
            join_to_send=self.supergroup and self.join_to_send,
            join_request=self.join_request,
            forum=False,
            stories_hidden=False,
            stories_hidden_min=True,
            stories_unavailable=True,
            access_hash=-1,
            restriction_reason=None,
            admin_rights=admin_rights,
            username=username,
            usernames=[],
            default_banned_rights=self.banned_rights.to_tl() if participant is not None else None,
            banned_rights=participant.banned_rights.to_tl() if participant is not None else None,
            color=PeerColor(color=self.accent_color_id) if self.accent_color_id is not None else None,
            profile_color=PeerColor(color=self.profile_color_id) if self.profile_color_id is not None else None,
            # NOTE: participants_count is not included here since it is present in ChannelFull
        )

    async def to_tl(self, user: models.User | int) -> TLChannel | ChannelForbidden:
        user_id = user.id if isinstance(user, models.User) else user

        peer_exists = await models.Peer.filter(owner__id=user_id, channel=self, type=PeerType.CHANNEL).exists()
        if self.deleted or not peer_exists:
            return ChannelForbidden(
                id=self.make_id(),
                access_hash=-1 if peer_exists is None else 0,
                title=self.name,
            )

        participant = await models.ChatParticipant.get_or_none(user__id=user_id, channel=self)
        if participant is None and not (self.nojoin_allow_view or await models.Username.filter(channel=self).exists()):
            return ChannelForbidden(
                id=self.make_id(),
                access_hash=-1,
                title=self.name,
            )

        username = await self.get_username()
        if self.photo is not None:
            self.photo = await self.photo

        return self._to_tl(user_id, participant, self.photo, username.username if username else None)

    # TODO: check if to_tl_bulk for one channel is slower than regular to_tl
    @classmethod
    async def to_tl_bulk(
            cls, channels: list[models.Channel], user: models.User
    ) -> list[TLChannel | ChannelForbidden]:
        if not channels:
            return []

        channel_ids = [channel.id for channel in channels]

        peers = set(await models.Peer.filter(owner=user, channel_id__in=channel_ids).values_list("channel__id"))

        participants = {
            participant.channel_id: participant
            for participant in await models.ChatParticipant.filter(user=user, channel__id__in=channel_ids)
        }

        usernames = {
            channel_id: username
            for channel_id, username in await models.Username.filter(
                channel__id__in=channel_ids,
            ).values_list("channel_id", "username")
        }

        channel_by_photo = {
            channel.photo_id: channel.id
            for channel in channels
            if channel.photo_id is not None and not isinstance(channel.photo, models.File)
        }
        photos = {
            channel_by_photo[photo.id]: photo
            for photo in await models.File.filter(id__in=list(channel_by_photo))
        }
        for channel in channels:
            if channel.photo_id is not None and isinstance(channel.photo, models.File):
                photos[channel.id] = channel.photo

        tl = []
        for channel in channels:
            peer_exists = channel.id in peers
            if channel.deleted or peer_exists:
                tl.append(ChannelForbidden(
                    id=channel.make_id(),
                    access_hash=-1 if peer_exists is None else 0,
                    title=channel.name,
                ))
                continue

            participant = participants.get(channel.id)

            if participant is None and not (channel.nojoin_allow_view or channel.id in usernames):
                tl.append(ChannelForbidden(
                    id=channel.make_id(),
                    access_hash=-1,
                    title=channel.name,
                ))
                continue

            tl.append(channel._to_tl(user.id, participant, photos.get(channel.id), usernames.get(channel.id)))

        return tl

    def min_id(self, participant: models.ChatParticipant) -> int | None:
        if participant is not None:
            return participant.min_message_id
        return self.min_available_id

    @staticmethod
    def make_access_hash(user: int, auth: int, channel: int) -> int:
        to_sign = AccessHashPayloadChannel(this_user_id=user, channel_id=channel, auth_id=auth).write()
        digest = hmac.new(AppConfig.HMAC_KEY, to_sign, hashlib.sha256).digest()
        return Long.read_bytes(digest[-8:])

    @staticmethod
    def check_access_hash(user: int, auth: int, channel: int, access_hash: int) -> bool:
        return Channel.make_access_hash(user, auth, channel) == access_hash
