from __future__ import annotations

from typing import TYPE_CHECKING, Callable, Iterable

from tortoise.expressions import Q
from tortoise.queryset import QuerySet

from piltover.db import models
from piltover.db.enums import PeerType
from piltover.tl.base import User as TLUserBase, Chat as TLChatBase
from piltover.tl.to_format import MessageToFormat, ChannelMessageToFormat
from piltover.tl.types import TLObject, Message, PeerChannel, PeerChat, PeerUser, MessageFwdHeader, \
    MessageMediaContact, MessageEntityMentionName, MessageReactions, MessagePeerReaction, MessageReactor, \
    MessageActionChannelMigrateFrom, MessageActionChatAddUser, MessageActionChatCreate, MessageActionChatDeleteUser, \
    MessageActionChatJoinedByLink, MessageActionChatMigrateTo, MessageActionGeoProximityReached, \
    MessageActionPaymentRefunded, MessageActionRequestedPeer
from piltover.tl.types.internal import MessageToFormatContent, MessageToFormatServiceContent

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
    __slots__ = ("_user_ids", "_chat_ids", "_channel_ids",)

    def __init__(self) -> None:
        self._user_ids: set[int] = set()
        self._chat_ids: set[int] = set()
        self._channel_ids: set[int] = set()

    def add_user(self, user_id: int) -> None:
        self._user_ids.add(user_id)

    def add_chat(self, chat_id: int) -> None:
        self._chat_ids.add(chat_id)

    def add_channel(self, channel_id: int) -> None:
        self._channel_ids.add(channel_id)

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

    def add_from_tl(self, obj: TLObject) -> None:
        self._visit_tl(obj)

    def _query(self) -> tuple[QsUser | None, QsChat | None, QsChannel | None]:
        if not self._user_ids \
                and not self._chat_ids \
                and not self._channel_ids:
            return None, None, None

        users_q: Q | None = None
        chats_q: Q | None = None
        channels_q: Q | None = None

        if self._user_ids:
            users_q = Q(id__in=self._user_ids)
        if self._chat_ids:
            chats_q = Q(id__in=self._chat_ids)
        if self._channel_ids:
            channels_q = Q(id__in=self._channel_ids)

        return (
            models.User.filter(users_q) if users_q is not None else None,
            models.Chat.filter(chats_q) if chats_q is not None else None,
            models.Channel.filter(channels_q) if channels_q is not None else None,
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

    def _visit_tl_Message(self, obj: Message) -> None:
        if obj.via_bot_id:
            self.add_user(obj.via_bot_id)

        self._visit_tl(obj.from_id)
        self._visit_tl(obj.peer_id)
        self._visit_tl(obj.saved_peer_id)
        self._visit_tl(obj.fwd_from)
        self._visit_tl(obj.media)
        self._visit_tlvec(obj.entities)
        self._visit_tl(obj.reactions)

    def _visit_tl_MessageToFormat(self, obj: MessageToFormat) -> None:
        self._visit_tl(obj.ref.peer_id)
        self._visit_tl(obj.content)

        if obj.replies is not None:
            self._visit_tlvec(obj.replies.recent_repliers)

        self._visit_tl(obj.reactions)

    def _visit_tl_MessageToFormatContent(self, obj: MessageToFormatContent) -> None:
        if obj.via_bot_id:
            self.add_user(obj.via_bot_id)

        self._visit_tl(obj.from_id)
        self._visit_tl(obj.media)
        self._visit_tl(obj.fwd_from)
        self._visit_tlvec(obj.entities)

    def _visit_tl_MessageToFormatServiceContent(self, obj: MessageToFormatServiceContent) -> None:
        self._visit_tl(obj.from_id)
        self._visit_tl(obj.action)

    def _visit_tl_MessageActionChannelMigrateFrom(self, obj: MessageActionChannelMigrateFrom) -> None:
        self.add_chat(models.Chat.norm_id(obj.chat_id))

    def _visit_tl_MessageActionChatAddUser(self, obj: MessageActionChatAddUser) -> None:
        for user_id in obj.users:
            self.add_user(user_id)

    def _visit_tl_MessageActionChatCreate(self, obj: MessageActionChatCreate) -> None:
        for user_id in obj.users:
            self.add_user(user_id)

    def _visit_tl_MessageActionChatDeleteUser(self, obj: MessageActionChatDeleteUser) -> None:
        self.add_user(obj.user_id)

    def _visit_tl_MessageActionChatJoinedByLink(self, obj: MessageActionChatJoinedByLink) -> None:
        self.add_user(obj.inviter_id)

    def _visit_tl_MessageActionChatMigrateTo(self, obj: MessageActionChatMigrateTo) -> None:
        self.add_channel(models.Channel.norm_id(obj.channel_id))

    def _visit_tl_MessageActionGeoProximityReached(self, obj: MessageActionGeoProximityReached) -> None:
        self._visit_tl(obj.from_id)
        self._visit_tl(obj.to_id)

    def _visit_tl_MessageActionPaymentRefunded(self, obj: MessageActionPaymentRefunded) -> None:
        self._visit_tl(obj.peer)

    def _visit_tl_MessageActionRequestedPeer(self, obj: MessageActionRequestedPeer) -> None:
        for peer in obj.peers:
            self._visit_tl(peer)

    def _visit_tl_ChannelMessageToFormat(self, obj: ChannelMessageToFormat) -> None:
        self.add_channel(obj.common.channel_id)
        self._visit_tl(obj.content)

        if obj.replies is not None:
            self._visit_tlvec(obj.replies.recent_repliers)

    def _visit_tl_PeerUser(self, obj: PeerUser) -> None:
        self.add_user(obj.user_id)

    def _visit_tl_PeerChat(self, obj: PeerChat) -> None:
        self.add_chat(models.Chat.norm_id(obj.chat_id))

    def _visit_tl_PeerChannel(self, obj: PeerChannel) -> None:
        self.add_channel(models.Channel.norm_id(obj.channel_id))

    def _visit_tl_MessageFwdHeader(self, obj: MessageFwdHeader) -> None:
        self._visit_tl(obj.from_id)
        self._visit_tl(obj.saved_from_id)
        self._visit_tl(obj.saved_from_peer)

    def _visit_tl_MessageMediaContact(self, obj: MessageMediaContact) -> None:
        self.add_user(obj.user_id)

    def _visit_tl_MessageEntityMentionName(self, obj: MessageEntityMentionName) -> None:
        self.add_user(obj.user_id)

    def _visit_tl_MessageReactions(self, obj: MessageReactions) -> None:
        self._visit_tlvec(obj.recent_reactions)
        self._visit_tlvec(obj.top_reactors)

    def _visit_tl_MessagePeerReaction(self, obj: MessagePeerReaction) -> None:
        self._visit_tl(obj.peer_id)

    def _visit_tl_MessageReactor(self, obj: MessageReactor) -> None:
        self._visit_tl(obj.peer_id)

    def _visit_tl(self, obj: TLObject | None) -> None:
        if obj is None or (visitor := self.__class__._tl_visitors.get(obj.tlid())) is None:
            return
        visitor(self, obj)

    def _visit_tlvec(self, vec: Iterable[TLObject] | None) -> None:
        if not vec:
            return
        for obj in vec:
            self._visit_tl(obj)

    _tl_visitors: dict[int, Callable[[UsersChatsChannels, TLObject], None]] = {
        Message.tlid(): _visit_tl_Message,
        PeerUser.tlid(): _visit_tl_PeerUser,
        PeerChat.tlid(): _visit_tl_PeerChat,
        PeerChannel.tlid(): _visit_tl_PeerChannel,
        MessageFwdHeader.tlid(): _visit_tl_MessageFwdHeader,
        MessageMediaContact.tlid(): _visit_tl_MessageMediaContact,
        MessageEntityMentionName.tlid(): _visit_tl_MessageEntityMentionName,
        MessageReactions.tlid(): _visit_tl_MessageReactions,
        MessagePeerReaction.tlid(): _visit_tl_MessagePeerReaction,
        MessageReactor.tlid(): _visit_tl_MessageReactor,
        MessageToFormat.tlid(): _visit_tl_MessageToFormat,
        MessageToFormatContent.tlid(): _visit_tl_MessageToFormatContent,
        MessageToFormatServiceContent.tlid(): _visit_tl_MessageToFormatServiceContent,
        ChannelMessageToFormat.tlid(): _visit_tl_ChannelMessageToFormat,
        MessageActionChannelMigrateFrom.tlid(): _visit_tl_MessageActionChannelMigrateFrom,
        MessageActionChatAddUser.tlid(): _visit_tl_MessageActionChatAddUser,
        MessageActionChatCreate.tlid(): _visit_tl_MessageActionChatCreate,
        MessageActionChatDeleteUser.tlid(): _visit_tl_MessageActionChatDeleteUser,
        MessageActionChatJoinedByLink.tlid(): _visit_tl_MessageActionChatJoinedByLink,
        MessageActionChatMigrateTo.tlid(): _visit_tl_MessageActionChatMigrateTo,
        MessageActionGeoProximityReached.tlid(): _visit_tl_MessageActionGeoProximityReached,
        MessageActionPaymentRefunded.tlid(): _visit_tl_MessageActionPaymentRefunded,
        MessageActionRequestedPeer.tlid(): _visit_tl_MessageActionRequestedPeer,
    }
