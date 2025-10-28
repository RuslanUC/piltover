from __future__ import annotations

from base64 import urlsafe_b64encode, urlsafe_b64decode
from datetime import datetime
from os import urandom

from tortoise import Model, fields
from tortoise.expressions import Q

from piltover.db import models
from piltover.tl import ChatInviteExported, Long


class ChatInvite(Model):
    id: int = fields.BigIntField(pk=True)
    revoked: bool = fields.BooleanField(default=False)
    expires_at: datetime | None = fields.DatetimeField(null=True, default=None)
    request_needed: bool = fields.BooleanField(default=False)
    nonce: str = fields.CharField(max_length=16, default=lambda: urandom(8).hex())
    user: models.User | None = fields.ForeignKeyField("models.User", null=True)
    chat: models.Chat | None = fields.ForeignKeyField("models.Chat", null=True)
    channel: models.Channel | None = fields.ForeignKeyField("models.Channel", null=True)
    created_at: datetime = fields.DatetimeField(auto_now_add=True)
    updated_at: datetime = fields.DatetimeField(auto_now_add=True)
    usage_limit: int | None = fields.IntField(null=True, default=None)
    usage: int = fields.IntField(default=0)
    title: str | None = fields.CharField(max_length=128, null=True)

    user_id: int | None
    chat_id: int | None
    channel_id: int | None

    def to_link_hash(self) -> str:
        return urlsafe_b64encode(Long.write(self.id) + bytes.fromhex(self.nonce)).decode("utf8").strip("=")

    @classmethod
    def query_from_link_hash(cls, link_nonce: str) -> Q:
        try:
            link_nonce = urlsafe_b64decode(link_nonce + "=" * (-len(link_nonce) % 4))
        except ValueError:
            return Q(id=0)

        if len(link_nonce) != 16:
            return Q(id=0)

        invite_id = Long.read_bytes(link_nonce[:8])
        nonce = link_nonce[8:].hex()

        return Q(id=invite_id, nonce=nonce)

    async def to_tl(self) -> ChatInviteExported:
        return ChatInviteExported(
            revoked=self.revoked,
            permanent=self.expires_at is None,
            request_needed=False,
            link=f"https://t.me/+{self.to_link_hash()}",
            admin_id=self.user_id or 0,
            date=int(self.created_at.timestamp()),
            start_date=int(self.updated_at.timestamp()),
            expire_date=None if self.expires_at is None else int(self.expires_at.timestamp()),
            usage_limit=self.usage_limit,
            usage=self.usage,
            requested=await models.ChatInviteRequest.filter(invite=self).count(),
            title=self.title,
        )

    def query_users_chats(
            self, users: Q | None = None, chats: Q | None = None, channels: Q | None = None,
    ) -> tuple[Q | None, Q | None, Q | None]:
        if users is not None and self.user_id is not None:
            users |= Q(id=self.user_id)
        if chats is not None and self.chat_id is not None:
            chats |= Q(id=self.chat_id)
        if chats is not None and self.channel_id is not None:
            channels |= Q(id=self.channel_id)

        return users, chats, channels

    @property
    def chat_or_channel(self) -> models.ChatBase:
        if self.chat_id is not None:
            return self.chat
        if self.channel_id is not None:
            return self.channel

        raise NotImplementedError

    @classmethod
    async def get_or_create_permanent(
            cls, user: models.User, chat_or_channel: models.ChatBase, request: bool = False,
            limit: int | None = None, title: str | None = None, force_create: bool = False,
    ) -> ChatInvite:
        if not force_create:
            invite = await cls.filter(
                **models.Chat.or_channel(chat_or_channel), user=user, revoked=False, expires_at__isnull=True
            ).first()
            if invite is not None:
                return invite

        return await ChatInvite.create(
            **models.Chat.or_channel(chat_or_channel),
            user=user,
            request_needed=request,
            usage_limit=limit if not request else None,
            title=title,
        )
