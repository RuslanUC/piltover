from __future__ import annotations

from datetime import datetime

from tortoise import fields, Model
from tortoise.expressions import Q
from tortoise.query_utils import Prefetch

from piltover.db import models
from piltover.db.enums import UpdateType, PeerType, NotifySettingsNotPeerType
from piltover.db.models.utils import NullableFK, NullableFKSetNull
from piltover.tl import UpdateEditMessage, UpdateReadHistoryInbox, UpdateDialogPinned, DialogPeer, \
    UpdateDialogFilterOrder, UpdateRecentReactions, UpdateNewScheduledMessage
from piltover.tl.base import Message as TLMessageBase
from piltover.tl.types import UpdateDeleteMessages, UpdatePinnedDialogs, UpdateDraftMessage, DraftMessageEmpty, \
    UpdatePinnedMessages, UpdateUser, UpdateChatParticipants, ChatParticipants, Username, \
    UpdateUserName, UpdatePeerSettings, PeerUser, PeerSettings, UpdatePeerBlocked, UpdateChat, UpdateDialogUnreadMark, \
    UpdateReadHistoryOutbox, UpdateFolderPeers, FolderPeer, UpdateChannel, UpdateReadChannelInbox, \
    UpdateMessagePoll, UpdateDialogFilter, UpdateEncryption, UpdateConfig, UpdateNewAuthorization, \
    UpdateNewStickerSet, UpdateStickerSets, UpdateStickerSetsOrder, UpdatePeerWallpaper, UpdateReadMessagesContents, \
    UpdateDeleteScheduledMessages, UpdatePeerHistoryTTL, UpdateBotCallbackQuery, UpdateUserPhone, UpdateNotifySettings, \
    UpdateSavedGifs, UpdateBotInlineQuery, UpdateRecentStickers, UpdateFavedStickers, UpdateSavedDialogPinned, \
    UpdatePinnedSavedDialogs, UpdatePrivacy, UpdateMessageID, UpdatePhoneCall, UpdateChannelAvailableMessages, \
    UpdateReadChannelOutbox, EmojiStatus, EmojiStatusEmpty, UpdateUserEmojiStatus
from piltover.utils.users_chats_channels import UsersChatsChannels

UpdateTypes = UpdateDeleteMessages | UpdateEditMessage | UpdateReadHistoryInbox | UpdateDialogPinned \
              | UpdatePinnedDialogs | UpdateDraftMessage | UpdatePinnedMessages | UpdateUser | UpdateChatParticipants \
              | UpdateUserName | UpdatePeerSettings | UpdatePeerBlocked | UpdateChat | UpdateDialogUnreadMark \
              | UpdateReadHistoryOutbox | UpdateFolderPeers | UpdateChannel | UpdateReadChannelInbox \
              | UpdateMessagePoll | UpdateDialogFilter | UpdateDialogFilterOrder | UpdateEncryption | UpdateConfig \
              | UpdateRecentReactions | UpdateNewAuthorization | UpdateNewStickerSet | UpdateStickerSets \
              | UpdateStickerSetsOrder | UpdatePeerWallpaper | UpdateReadMessagesContents | UpdateNewScheduledMessage \
              | UpdateDeleteScheduledMessages | UpdatePeerHistoryTTL | UpdateBotCallbackQuery | UpdateUserPhone \
              | UpdateNotifySettings | UpdateSavedGifs | UpdateBotInlineQuery | UpdateRecentStickers \
              | UpdateFavedStickers | UpdateSavedDialogPinned | UpdatePinnedSavedDialogs | UpdatePrivacy \
              | UpdateMessageID | UpdatePhoneCall | UpdateChannelAvailableMessages | UpdateReadChannelOutbox \
              | UpdateUserEmojiStatus


class Update(Model):
    id: int = fields.BigIntField(primary_key=True)
    update_type: UpdateType = fields.IntEnumField(UpdateType, description="")
    pts: int = fields.BigIntField(db_index=True)
    pts_count: int = fields.IntField(default=0)
    date: datetime = fields.DatetimeField(auto_now_add=True)
    related_id: int = fields.BigIntField(db_index=True, null=True)
    # TODO: probably there is a better way to store multiple updates (right now it is only used for deleted messages,
    #  so maybe create two tables: something like UpdateDeletedMessage and UpdateDeletedMessageId,
    #  related_id will point to UpdateDeletedMessage.id
    #  and UpdateDeletedMessage will have one-to-many relation to UpdateDeletedMessageId)
    related_ids: list[int] = fields.JSONField(null=True, default=None)
    additional_data: list | dict = fields.JSONField(null=True, default=None)
    user: models.User = fields.ForeignKeyField("models.User", related_name="updates")

    peer: models.Peer | None = NullableFK("models.Peer")
    update_user: models.User | None = NullableFK("models.User", related_name="updated")
    dialog: models.Dialog | None = NullableFK("models.Dialog")
    draft: models.MessageDraft | None = NullableFKSetNull("models.MessageDraft")
    message: models.MessageRef | None = NullableFK("models.MessageRef")
    encrypted_chat: models.EncryptedChat | None = NullableFK("models.EncryptedChat")
    authorization: models.UserAuthorization | None = NullableFK("models.UserAuthorization")
    stickerset: models.Stickerset | None = NullableFK("models.Stickerset")

    user_id: int
    peer_id: int | None
    update_user_id: int | None
    dialog_id: int | None
    draft_id: int | None
    message_id: int | None
    encrypted_chat_id: int | None
    authorization_id: int | None
    stickerset_id: int | None

    MESSAGE_PREFETCH_MAYBECACHED = ("message", "message__peer", "message__content", "message__peer__channel")

    # TODO: add to_tl_bulk

    async def to_tl(
            self, user_id: int, formatted_messages: dict[int, TLMessageBase], auth_id: int | None,
            ucc: UsersChatsChannels,
    ) -> UpdateTypes | None:

        match self.update_type:
            case UpdateType.MESSAGE_DELETE:
                return UpdateDeleteMessages(
                    messages=self.related_ids,
                    pts=self.pts,
                    pts_count=len(self.related_ids),
                )

            case UpdateType.MESSAGE_EDIT:
                if self.message is None:
                    return None

                ucc.add_message(self.message.content_id)

                return UpdateEditMessage(
                    message=formatted_messages[self.message_id],
                    pts=self.pts,
                    pts_count=1,
                )

            case UpdateType.DIALOG_PIN:
                if self.peer is None or self.dialog is None or not self.dialog.visible:
                    return None

                ucc.add_peer(self.peer)

                return UpdateDialogPinned(
                    pinned=self.dialog.pinned_index is not None,
                    peer=DialogPeer(
                        peer=self.peer.to_tl(),
                    ),
                )

            case UpdateType.DIALOG_PIN_REORDER:
                dialogs = await models.Dialog.filter(
                    peer__owner_id=user_id, pinned_index__not_isnull=True, visible=True,
                ).select_related("peer")

                for dialog in dialogs:
                    ucc.add_peer(dialog.peer)

                return UpdatePinnedDialogs(
                    order=[
                        DialogPeer(peer=dialog.peer.to_tl())
                        for dialog in dialogs
                    ],
                )

            case UpdateType.DRAFT_UPDATE:
                if self.peer is None:
                    return None

                ucc.add_peer(self.peer)

                if isinstance(self.draft, models.MessageDraft):
                    draft = self.draft.to_tl()
                else:
                    draft = DraftMessageEmpty()

                return UpdateDraftMessage(
                    peer=self.peer.to_tl(),
                    draft=draft,
                )

            case UpdateType.USER_UPDATE:
                ucc.add_user(self.related_id)
                return UpdateUser(user_id=self.related_id)

            case UpdateType.CHAT_CREATE:
                chat = await models.Chat.get_or_none(
                    id=self.related_id,
                    deleted=False,
                    peers__owner_id=user_id,
                ).prefetch_related(
                    Prefetch(
                        "chatparticipants",
                        queryset=models.ChatParticipant.filter(left=False).only(
                            "user_id", "admin_rights", "inviter_id", "invited_at",
                        )
                    ),
                )

                if chat is None:
                    return None

                ucc.add_chat(chat.id)

                participants = []
                for participant in chat.chatparticipants:
                    participants.append(participant.to_tl_chat_with_creator(chat.creator_id))
                    ucc.add_user(participant.user_id)

                return UpdateChatParticipants(
                    participants=ChatParticipants(
                        chat_id=chat.id,
                        participants=participants,
                        version=1,
                    ),
                )

            case UpdateType.USER_UPDATE_NAME:
                # TODO: prefetch user
                if (target := await models.User.get_or_none(id=self.related_id).select_related("username")) is None:
                    return None

                ucc.add_user(target.id)

                return UpdateUserName(
                    user_id=target.id,
                    first_name=target.first_name,
                    last_name=target.last_name or "",
                    usernames=[
                        Username(editable=True, active=True, username=target.username.username)
                    ] if target.username else [],
                )

            case UpdateType.UPDATE_CONTACT:
                if self.update_user_id is None:
                    return None

                ucc.add_user(self.update_user_id)

                return UpdatePeerSettings(
                    peer=PeerUser(user_id=self.update_user_id),
                    settings=PeerSettings(),
                )

            case UpdateType.UPDATE_BLOCK:
                if self.peer is None:
                    return None

                ucc.add_peer(self.peer)

                return UpdatePeerBlocked(
                    peer_id=self.peer.to_tl(),
                    blocked=self.peer.blocked_at is not None,
                )

            case UpdateType.UPDATE_CHAT:
                ucc.add_chat(self.related_id)
                return UpdateChat(chat_id=self.related_id)

            case UpdateType.UPDATE_DIALOG_UNREAD_MARK:
                if self.peer is None or self.dialog is None or not self.dialog.visible:
                    return None

                ucc.add_peer(self.peer)

                return UpdateDialogUnreadMark(
                    peer=DialogPeer(peer=self.peer.to_tl()),
                    unread=self.dialog.unread_mark,
                )

            case UpdateType.READ_INBOX:
                if not self.additional_data or len(self.additional_data) != 2:
                    return None
                if self.peer is None:
                    return None

                ucc.add_peer(self.peer)

                if self.peer.type is PeerType.CHANNEL:
                    return UpdateReadChannelInbox(
                        channel_id=self.peer.channel_id,
                        max_id=self.additional_data[0],
                        still_unread_count=self.additional_data[1],
                        pts=self.pts,
                    )

                return UpdateReadHistoryInbox(
                    peer=self.peer.to_tl(),
                    max_id=self.additional_data[0],
                    still_unread_count=self.additional_data[1],
                    pts=self.pts,
                    pts_count=self.pts_count,
                )

            case UpdateType.READ_INBOX_CHANNEL:
                if not self.additional_data or len(self.additional_data) != 2:
                    return None

                ucc.add_channel(self.related_id)
                return UpdateReadChannelInbox(
                    channel_id=self.related_id,
                    max_id=self.additional_data[0],
                    still_unread_count=self.additional_data[1],
                    pts=self.pts,
                )

            case UpdateType.READ_OUTBOX:
                if not self.additional_data or len(self.additional_data) != 1:
                    return None
                if self.peer is None:
                    return None

                ucc.add_peer(self.peer)

                return UpdateReadHistoryOutbox(
                    peer=self.peer.to_tl(),
                    max_id=self.additional_data[0],
                    pts=self.pts,
                    pts_count=self.pts_count,
                )

            case UpdateType.READ_OUTBOX_CHANNEL:
                if not self.additional_data or len(self.additional_data) != 1:
                    return None

                ucc.add_channel(self.related_id)
                return UpdateReadChannelOutbox(
                    channel_id=self.related_id,
                    max_id=self.additional_data[0],
                )

            case UpdateType.FOLDER_PEERS:
                folder_peers = []

                dialog: models.Dialog
                async for dialog in models.Dialog.filter(
                        peer_id__in=self.related_ids, visible=True,
                ).select_related("peer"):
                    folder_peers.append(FolderPeer(peer=dialog.peer.to_tl(), folder_id=dialog.folder_id.value))
                    ucc.add_peer(dialog.peer)

                return UpdateFolderPeers(
                    folder_peers=folder_peers,
                    pts=self.pts,
                    pts_count=self.pts_count,
                )

            case UpdateType.UPDATE_CHANNEL:
                ucc.add_channel(self.related_id)
                return UpdateChannel(
                    channel_id=self.related_id,
                )

            case UpdateType.UPDATE_POLL:
                if (poll := await models.Poll.get_or_none(id=self.related_id).prefetch_related("pollanswers")) is None:
                    return None

                return UpdateMessagePoll(
                    poll_id=poll.id,
                    poll=poll.to_tl(),
                    results=await poll.to_tl_results(),
                )

            case UpdateType.UPDATE_FOLDER:
                folder_id_for_user = self.related_ids[0]
                folder = None
                if self.related_id is not None:
                    folder = await models.DialogFolder.get_or_none(
                        owner_id=user_id, id=self.related_id, id_for_user=folder_id_for_user,
                    ).prefetch_related("pinned_peers", "include_peers", "exclude_peers")

                return UpdateDialogFilter(
                    id=folder_id_for_user,
                    filter=folder.to_tl() if folder is not None else None,
                )

            case UpdateType.FOLDERS_ORDER:
                return UpdateDialogFilterOrder(order=self.related_ids)

            case UpdateType.UPDATE_ENCRYPTION:
                if auth_id is None:
                    return None

                if self.encrypted_chat is None:
                    return None

                if user_id == self.encrypted_chat.to_user_id:
                    other_user_id = self.encrypted_chat.from_user_id
                else:
                    other_user_id = self.encrypted_chat.to_user_id

                ucc.add_user(other_user_id)

                return UpdateEncryption(
                    chat=self.encrypted_chat.to_tl(),
                    date=int(self.date.timestamp()),
                )

            case UpdateType.UPDATE_CONFIG:
                return UpdateConfig()

            case UpdateType.UPDATE_RECENT_REACTIONS:
                return UpdateRecentReactions()

            case UpdateType.NEW_AUTHORIZATION:
                if self.authorization is None:
                    return None

                unconfirmed = not self.authorization.confirmed
                return UpdateNewAuthorization(
                    unconfirmed=unconfirmed,
                    hash=self.authorization.tl_hash,
                    date=int(self.authorization.created_at.timestamp()) if unconfirmed else None,
                    device=self.authorization.device_model if unconfirmed else None,
                    location=self.authorization.ip if unconfirmed else None,
                )

            case UpdateType.NEW_STICKERSET:
                if self.stickerset is None or self.stickerset.deleted:
                    return None

                return UpdateNewStickerSet(
                    stickerset=await self.stickerset.to_tl_messages(),
                )

            case UpdateType.UPDATE_STICKERSETS:
                return UpdateStickerSets()

            case UpdateType.UPDATE_STICKERSETS_ORDER:
                if not self.related_ids:
                    return None

                return UpdateStickerSetsOrder(
                    order=self.related_ids,
                )

            case UpdateType.UPDATE_CHAT_WALLPAPER:
                if self.related_ids:
                    chat_wallpaper = await models.ChatWallpaper.get_or_none(
                        user_id=user_id, wallpaper_id=self.related_ids[0],
                    ).select_related("wallpaper", "wallpaper__document", "wallpaper__settings")
                    wallpaper = chat_wallpaper.wallpaper if chat_wallpaper is not None else None
                else:
                    wallpaper = None
                    chat_wallpaper = None

                ucc.add_user(self.related_id)

                return UpdatePeerWallpaper(
                    wallpaper_overridden=chat_wallpaper.overridden if chat_wallpaper is not None else False,
                    peer=PeerUser(user_id=self.related_id),
                    wallpaper=wallpaper.to_tl() if wallpaper is not None else None,
                )

            case UpdateType.READ_MESSAGES_CONTENTS:
                if not self.related_ids:
                    return None

                return UpdateReadMessagesContents(
                    messages=self.related_ids,
                    pts=self.pts,
                    pts_count=self.pts_count,
                    date=int(self.date.timestamp()),
                )

            case UpdateType.NEW_SCHEDULED_MESSAGE:
                if self.message is None:
                    return None

                ucc.add_message(self.message.content_id)

                return UpdateNewScheduledMessage(message=formatted_messages[self.message_id])

            case UpdateType.DELETE_SCHEDULED_MESSAGE:
                if self.peer is None:
                    return None

                deleted_message_ids = self.related_ids[:self.pts_count]
                sent_message_ids = self.related_ids[self.pts_count:]

                return UpdateDeleteScheduledMessages(
                    peer=self.peer.to_tl(),
                    messages=deleted_message_ids,
                    sent_messages=sent_message_ids or None,
                )

            case UpdateType.UPDATE_HISTORY_TTL:
                if self.peer is None:
                    return None

                ttl_days = self.additional_data[0]
                return UpdatePeerHistoryTTL(
                    peer=self.peer.to_tl(),
                    ttl_period=ttl_days * 86400 if ttl_days else None,
                )

            case UpdateType.BOT_CALLBACK_QUERY:
                query = await models.CallbackQuery.get_or_none(id=self.related_id, inline=False).select_related(
                    "message", "message__peer",
                )
                if query is None:
                    return None

                ucc.add_message_ref(query.message_id)

                return UpdateBotCallbackQuery(
                    query_id=query.id,
                    user_id=query.user_id,
                    peer=query.message.peer.to_tl(),
                    msg_id=query.message_id,
                    chat_instance=0,
                    data=query.data,
                )

            case UpdateType.UPDATE_PHONE:
                # TODO: use update_user
                if (update_user := await models.User.get_or_none(id=self.related_id)) is None:
                    return None

                ucc.add_user(self.related_id)

                return UpdateUserPhone(
                    user_id=self.related_id,
                    phone=update_user.phone_number,
                )

            case UpdateType.UPDATE_PEER_NOTIFY_SETTINGS:
                peer = not_peer = None
                if self.related_id is not None:
                    settings = await models.PeerNotifySettings.get_or_none(
                        user_id=user_id, peer__owner_id=user_id, peer_id=self.related_id,
                    ).select_related("peer")
                    if settings is not None and settings.peer is not None:
                        peer = settings.peer
                        ucc.add_peer(settings.peer)
                elif self.additional_data and self.additional_data[0] in NotifySettingsNotPeerType._value2member_map_:
                    settings = await models.PeerNotifySettings.get_or_none(
                        user_id=user_id, peer=None, not_peer=NotifySettingsNotPeerType(self.additional_data[0]),
                    ).select_related("peer")
                    not_peer = settings.not_peer
                else:
                    return None

                if settings is None:
                    return None

                return UpdateNotifySettings(
                    peer=models.PeerNotifySettings.peer_to_tl(peer, not_peer),
                    notify_settings=settings.to_tl(),
                )

            case UpdateType.SAVED_GIFS:
                return UpdateSavedGifs()

            case UpdateType.BOT_INLINE_QUERY:
                query = await models.InlineQuery.get_or_none(id=self.related_id, bot_id=user_id)
                if query is None:
                    return None

                ucc.add_user(query.user_id)

                return UpdateBotInlineQuery(
                    query_id=query.id,
                    user_id=query.user_id,
                    query=query.query,
                    peer_type=models.InlineQuery.INLINE_PEER_TO_TL[query.inline_peer],
                    offset=query.offset,
                )

            case UpdateType.UPDATE_RECENT_STICKERS:
                return UpdateRecentStickers()

            case UpdateType.UPDATE_FAVED_STICKERS:
                return UpdateFavedStickers()

            case UpdateType.SAVED_DIALOG_PIN:
                saved_dialog = await models.SavedDialog.get_or_none(
                    peer__owner_id=user_id, peer_id=self.related_id,
                ).select_related("peer")
                if saved_dialog is None:
                    return None

                ucc.add_peer(saved_dialog.peer)

                return UpdateSavedDialogPinned(
                    pinned=saved_dialog.pinned_index is not None,
                    peer=DialogPeer(peer=saved_dialog.peer.to_tl()),
                )

            case UpdateType.SAVED_DIALOG_PIN_REORDER:
                dialogs = await models.SavedDialog.filter(
                    peer__owner_id=user_id, pinned_index__not_isnull=True,
                ).select_related("peer")

                for dialog in dialogs:
                    ucc.add_peer(dialog.peer)

                return UpdatePinnedSavedDialogs(
                    order=[
                        DialogPeer(peer=dialog.peer.to_tl())
                        for dialog in dialogs
                    ],
                )

            case UpdateType.UPDATE_PRIVACY:
                rule = await models.PrivacyRule.get_or_none(
                    user_id=user_id, id=self.related_id,
                ).prefetch_related("exceptions")
                if rule is None:
                    return None

                for exc in rule.exceptions:
                    if exc.user_id is not None:
                        ucc.add_user(exc.user_id)

                return UpdatePrivacy(
                    key=rule.key.to_tl(),
                    rules=rule.to_tl_rules(),
                )

            case UpdateType.NEW_MESSAGE:
                return None  # Handled in GetDifference

            case UpdateType.UPDATE_MESSAGE_ID:
                return UpdateMessageID(
                    id=self.related_id,
                    random_id=self.related_ids[0],
                )

            case UpdateType.PHONE_CALL:
                call = await models.PhoneCall.get_or_none(
                    Q(from_user_id=user_id) | Q(to_user_id=user_id), id=self.related_id
                )
                if call is None:
                    return None

                ucc.add_user(call.from_user_id)
                ucc.add_user(call.to_user_id)

                return UpdatePhoneCall(
                    phone_call=call.to_tl(),
                )

            case UpdateType.UPDATE_CHANNEL_MIN_AVAILABLE_ID:
                if not self.additional_data:
                    return None

                ucc.add_channel(self.related_id)

                return UpdateChannelAvailableMessages(
                    channel_id=models.Channel.make_id_from(self.related_id),
                    available_min_id=self.additional_data[0],
                )

            case UpdateType.PIN_MESSAGES | UpdateType.UNPIN_MESSAGES:
                if self.peer is None:
                    return None

                ucc.add_peer(self.peer)

                return UpdatePinnedMessages(
                    pinned=self.update_type is UpdateType.PIN_MESSAGES,
                    peer=self.peer.to_tl(),
                    messages=self.related_ids,
                    pts=self.pts,
                    pts_count=self.pts_count,
                )

            case UpdateType.EMOJI_STATUS:
                if self.related_id:
                    until = self.additional_data[0] if self.additional_data else None
                    status = EmojiStatus(document_id=self.related_id, until=until)
                else:
                    status = EmojiStatusEmpty()

                ucc.add_user(user_id)

                return UpdateUserEmojiStatus(
                    user_id=user_id,
                    emoji_status=status,
                )

        return None
