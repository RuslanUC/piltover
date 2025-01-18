from __future__ import annotations

from time import time

from tortoise import fields, Model

from piltover.db import models
from piltover.db.enums import PeerType
from piltover.tl import ChatPhoto, ChatForbidden
from piltover.tl.types import Chat as TLChat, ChatPhotoEmpty, ChatBannedRights

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


class Chat(Model):
    id: int = fields.BigIntField(pk=True)
    name: str = fields.CharField(max_length=64)
    description: str = fields.CharField(max_length=255, default="")
    version: int = fields.BigIntField(default=1)
    creator: models.User = fields.ForeignKeyField("models.User")
    photo: models.File = fields.ForeignKeyField("models.File", on_delete=fields.SET_NULL, null=True, default=None)

    creator_id: int
    photo_id: int

    async def to_tl(self, user: models.User) -> TLChat | ChatForbidden:
        if not await models.ChatParticipant.filter(user=user, chat=self).exists():
            return ChatForbidden(id=self.id, title=self.name)

        photo = ChatPhotoEmpty()
        if self.photo_id:
            self.photo = await self.photo
            photo = ChatPhoto(
                has_video=False, photo_id=self.photo.id, dc_id=2, stripped_thumb=self.photo.photo_stripped,
            )

        return TLChat(
            creator=self.creator == user,
            left=False,
            deactivated=False,
            call_active=False,
            call_not_empty=False,
            noforwards=False,
            id=self.id,
            title=self.name,
            photo=photo,
            participants_count=await models.Peer.filter(chat=self, type=PeerType.CHAT).count(),
            date=int(time()),  # ??
            version=self.version,
            migrated_to=None,
            admin_rights=None,
            default_banned_rights=DEFAULT_BANNED_RIGHTS,
        )
