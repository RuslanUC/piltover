from __future__ import annotations

from typing import TYPE_CHECKING

from tortoise.expressions import Q, Subquery
from tortoise.queryset import QuerySet

from piltover.db import models
from piltover.db.enums import PeerType
from piltover.tl.base import User as TLUserBase, Chat as TLChatBase


_EMPTY = Q()
if TYPE_CHECKING:
    QsUser = QuerySet[models.User]
    QsChat = QuerySet[models.Chat]
    QsChannel = QuerySet[models.Channel]

USER_SELECT_RELATED = ("username", "background_emojis", "emoji_status", "presence",)
CHAT_SELECT_RELATED = ("photo",)
CHANNEL_SELECT_RELATED = ("photo",)

USER_SELECT_ONLY = (
    "id", "version", "bot", "accent_color_id", "profile_color_id", "first_name", "last_name", "phone_number",
    "lang_code",

    "background_emojis__id", "background_emojis__accent_emoji_id", "background_emojis__profile_emoji_id",
    "bot_info__id", "bot_info__version",
    "emoji_status__id", "emoji_status__emoji_id", "emoji_status__until",
    "presence__id", "presence__last_seen",
)
CHAT_SELECT_ONLY = (
    "id", "version", "deleted", "migrated", "photo_id", "name", "creator_id", "no_forwards", "participants_count",
    "created_at", "banned_rights",

    "photo__id", "photo__photo_stripped",
)
CHANNEL_SELECT_ONLY = (
    "id", "version", "deleted", "photo_id", "name", "accent_color_id", "profile_color_id", "accent_emoji_id",
    "profile_emoji_id", "created_at", "creator_id", "channel", "supergroup", "signatures", "discussion_id",
    "is_discussion", "slowmode_seconds", "no_forwards", "join_to_send", "join_request", "banned_rights",
    "nojoin_allow_view",

    "photo__id", "photo__photo_stripped",
)


class UsersChatsChannels:
    def __init__(self) -> None:
        self._user_ids: set[int] = set()
        self._chat_ids: set[int] = set()
        self._channel_ids: set[int] = set()
        self._message_ids: set[int] = set()

    def add_user(self, user_id: int) -> None:
        self._user_ids.add(user_id)

    def add_chat(self, chat_id: int) -> None:
        self._chat_ids.add(chat_id)

    def add_channel(self, channel_id: int) -> None:
        self._channel_ids.add(channel_id)

    def add_message(self, message_id: int) -> None:
        self._message_ids.add(message_id)

    def add_peer(self, peer: models.Peer) -> None:
        peer_type = peer.type
        if peer_type in (PeerType.SELF, PeerType.USER):
            self._user_ids.add(peer.user_id)
        elif peer_type is PeerType.CHAT:
            self._chat_ids.add(peer.chat_id)
        elif peer_type is PeerType.CHANNEL:
            self._channel_ids.add(peer.channel_id)

    def add_chat_invite(self, invite: models.ChatInvite) -> None:
        if invite.user_id is not None:
            self._user_ids.add(invite.user_id)
        if invite.chat_id is not None:
            self._chat_ids.add(invite.chat_id)
        if invite.channel_id is not None:
            self._channel_ids.add(invite.channel_id)

    def _query(self) -> tuple[QsUser | None, QsChat | None, QsChannel | None]:
        if not self._user_ids \
                and not self._chat_ids \
                and not self._channel_ids \
                and not self._message_ids:
            return None, None, None

        users_q = Q()
        chats_q = Q()
        channels_q = Q()

        if self._user_ids:
            users_q |= Q(id__in=self._user_ids)
        if self._chat_ids:
            chats_q |= Q(id__in=self._chat_ids)
        if self._channel_ids:
            channels_q |= Q(id__in=self._channel_ids)

        if self._message_ids:
            # TODO: there's probably a better solution
            base_messagerelated_query = models.MessageRelated.filter(message_id__in=self._message_ids).distinct()
            users_q |= Q(id__in=Subquery(base_messagerelated_query.values("user_id")))
            chats_q |= Q(id__in=Subquery(base_messagerelated_query.values("chat_id")))
            channels_q |= Q(id__in=Subquery(base_messagerelated_query.values("channel_id")))

        return (
            models.User.filter(users_q) if users_q != _EMPTY else None,
            models.Chat.filter(chats_q) if chats_q != _EMPTY else None,
            models.Channel.filter(channels_q) if channels_q != _EMPTY else None,
        )

    async def _resolve_nontl(
            self, fetch_users: bool = True, fetch_chats: bool = True, fetch_channels: bool = True
    ) -> tuple[list[models.User], list[models.Chat], list[models.Channel]]:
        users_q, chats_q, channels_q = self._query()

        return (
            await users_q.select_related(*USER_SELECT_RELATED).only(*USER_SELECT_ONLY) if fetch_users and users_q else [],
            await chats_q.select_related(*CHAT_SELECT_RELATED).only(*CHAT_SELECT_ONLY) if fetch_chats and chats_q else [],
            await channels_q.select_related(*CHANNEL_SELECT_RELATED).only(*CHANNEL_SELECT_ONLY) if fetch_channels and channels_q else [],
        )

    async def resolve(
            self, fetch_users: bool = True, fetch_chats: bool = True, fetch_channels: bool = True,
    ) -> tuple[list[TLUserBase], list[TLChatBase], list[TLChatBase]]:
        users, chats, channels = await self._resolve_nontl(fetch_users, fetch_chats, fetch_channels)

        return (
            await models.User.to_tl_bulk(users),
            await models.Chat.to_tl_bulk(chats),
            await models.Channel.to_tl_bulk(channels),
        )
