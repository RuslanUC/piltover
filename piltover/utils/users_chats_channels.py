from __future__ import annotations

from typing import TYPE_CHECKING

from tortoise.expressions import Q, Subquery
from tortoise.queryset import QuerySet

from piltover.db import models
from piltover.db.enums import PeerType
from piltover.tl import User as TLUser, Chat as TLChat, Channel as TLChannel


_EMPTY = Q()
if TYPE_CHECKING:
    QsUser = QuerySet[models.User]
    QsChat = QuerySet[models.Chat]
    QsChannel = QuerySet[models.Channel]


class UsersChatsChannels:
    def __init__(self):
        self._user_ids: set[int] = set()
        self._chat_ids: set[int] = set()
        self._channel_ids: set[int] = set()
        self._message_ids: set[int] = set()
        self._peer_ids: dict[PeerType, set[int]] = {}

    def add_user(self, user_id: int) -> None:
        self._user_ids.add(user_id)

    def add_chat(self, chat_id: int) -> None:
        self._chat_ids.add(chat_id)

    def add_channel(self, channel_id: int) -> None:
        self._channel_ids.add(channel_id)

    def add_message(self, message_id: int) -> None:
        self._message_ids.add(message_id)

    def add_peer(self, peer: models.Peer) -> None:
        # TODO: probably should also fetch all chat participants

        peer_type = peer.type
        if peer_type is PeerType.SELF:
            peer_type = PeerType.USER

        if peer_type not in self._peer_ids:
            self._peer_ids[peer_type] = set()
        self._peer_ids[peer_type].add(peer.id)

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
                and not self._message_ids \
                and not self._peer_ids:
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

        if self._message_ids is not None:
            base_query = models.MessageRelated.filter(message__id__in=self._message_ids)
            users_q |= Q(id__in=Subquery(base_query.values_list("user__id")))
            chats_q |= Q(id__in=Subquery(base_query.values_list("chat__id")))
            channels_q |= Q(id__in=Subquery(base_query.values_list("channel__id")))

        if PeerType.USER in self._peer_ids:
            users_q |= Q(id__in=Subquery(
                models.Peer.filter(id__in=self._peer_ids[PeerType.USER]).values_list("user__id")
            ))
        if PeerType.CHAT in self._peer_ids:
            chats_q |= Q(id__in=Subquery(
                models.Peer.filter(id__in=self._peer_ids[PeerType.CHAT]).values_list("chat__id")
            ))
        if PeerType.CHANNEL in self._peer_ids:
            channels_q |= Q(id__in=Subquery(
                models.Peer.filter(id__in=self._peer_ids[PeerType.CHANNEL]).values_list("channel__id")
            ))

        return (
            models.User.filter(users_q) if users_q != _EMPTY else None,
            models.Chat.filter(chats_q) if chats_q != _EMPTY else None,
            models.Channel.filter(channels_q) if channels_q != _EMPTY else None,
        )

    async def resolve_ids(self) -> tuple[list[int], list[int], list[int]]:
        users_q, chats_q, channels_q = self._query()

        return (
            await users_q.values_list("id", flat=True) if users_q else [],
            await chats_q.values_list("id", flat=True) if chats_q else [],
            await channels_q.values_list("id", flat=True) if channels_q else [],
        )

    async def resolve_nontl(
            self, fetch_users: bool = True, fetch_chats: bool = True, fetch_channels: bool = True
    ) -> tuple[list[models.User], list[models.Chat], list[models.Channel]]:
        users_q, chats_q, channels_q = self._query()

        return (
            await users_q if fetch_users and users_q else [],
            await chats_q if fetch_chats and chats_q else [],
            await channels_q if fetch_channels and channels_q else [],
        )

    async def resolve(
            self, current_user: models.User, fetch_users: bool = True, fetch_chats: bool = True,
            fetch_channels: bool = True,
    ) -> tuple[list[TLUser], list[TLChat], list[TLChannel]]:
        users, chats, channels = await self.resolve_nontl(fetch_users, fetch_chats, fetch_channels)

        return (
            await models.User.to_tl_bulk(users, current_user),
            await models.Chat.to_tl_bulk(chats, current_user),
            await models.Channel.to_tl_bulk(channels, current_user),
        )
