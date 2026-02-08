from __future__ import annotations

from datetime import datetime

from tortoise import fields, Model
from tortoise.expressions import Q

from piltover.db import models
from piltover.db.enums import UpdateType, PeerType, MessageType, NotifySettingsNotPeerType
from piltover.tl import UpdateEditMessage, UpdateReadHistoryInbox, UpdateDialogPinned, DialogPeer, \
    UpdateDialogFilterOrder, UpdateRecentReactions, UpdateNewScheduledMessage
from piltover.tl.types import UpdateDeleteMessages, UpdatePinnedDialogs, UpdateDraftMessage, DraftMessageEmpty, \
    UpdatePinnedMessages, UpdateUser, UpdateChatParticipants, ChatParticipants, ChatParticipantCreator, Username, \
    UpdateUserName, UpdatePeerSettings, PeerUser, PeerSettings, UpdatePeerBlocked, UpdateChat, UpdateDialogUnreadMark, \
    UpdateReadHistoryOutbox, ChatParticipant, UpdateFolderPeers, FolderPeer, UpdateChannel, UpdateReadChannelInbox, \
    UpdateMessagePoll, UpdateDialogFilter, UpdateEncryption, UpdateConfig, UpdateNewAuthorization, \
    UpdateNewStickerSet, UpdateStickerSets, UpdateStickerSetsOrder, UpdatePeerWallpaper, UpdateReadMessagesContents, \
    UpdateDeleteScheduledMessages, UpdatePeerHistoryTTL, UpdateBotCallbackQuery, UpdateUserPhone, UpdateNotifySettings, \
    UpdateSavedGifs, UpdateBotInlineQuery, UpdateRecentStickers, UpdateFavedStickers, UpdateSavedDialogPinned, \
    UpdatePinnedSavedDialogs, UpdatePrivacy, UpdateMessageID, UpdatePhoneCall, UpdateChannelAvailableMessages
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
              | UpdateMessageID | UpdatePhoneCall | UpdateChannelAvailableMessages


class Update(Model):
    id: int = fields.BigIntField(pk=True)
    update_type: UpdateType = fields.IntEnumField(UpdateType, description="")
    pts: int = fields.BigIntField()
    pts_count: int = fields.IntField(default=0)
    date: datetime = fields.DatetimeField(auto_now_add=True)
    related_id: int = fields.BigIntField(index=True, null=True)
    # TODO: probably there is a better way to store multiple updates (right now it is only used for deleted messages,
    #  so maybe create two tables: something like UpdateDeletedMessage and UpdateDeletedMessageId,
    #  related_id will point to UpdateDeletedMessage.id
    #  and UpdateDeletedMessage will have one-to-many relation to UpdateDeletedMessageId)
    related_ids: list[int] = fields.JSONField(null=True, default=None)
    additional_data: list | dict = fields.JSONField(null=True, default=None)
    user: models.User = fields.ForeignKeyField("models.User")

    # TODO: add to_tl_bulk

    async def to_tl(
            self, user: models.User, auth_id: int | None = None, ucc: UsersChatsChannels | None = None,
    ) -> UpdateTypes | None:

        match self.update_type:
            case UpdateType.MESSAGE_DELETE:
                return UpdateDeleteMessages(
                    messages=self.related_ids,
                    pts=self.pts,
                    pts_count=len(self.related_ids),
                )
            case UpdateType.MESSAGE_EDIT:
                message = await models.MessageRef.get_or_none(id=self.related_id).select_related(
                    *models.MessageRef.PREFETCH_FIELDS,
                )
                if message is None:
                    return None

                ucc.add_message(message.content_id)

                return UpdateEditMessage(
                    message=await message.to_tl(user),
                    pts=self.pts,
                    pts_count=1,
                )

            case UpdateType.READ_HISTORY_INBOX:
                query = Q(owner=user)
                if self.related_id:
                    query &= Q(user__id=self.related_id) | Q(chat__id=self.related_id)
                else:
                    query &= Q(type=PeerType.SELF)
                if (peer := await models.Peer.get_or_none(query)) is None:
                    return None

                ucc.add_peer(peer)

                # TODO: fetch read state from db instead of related_ids
                return UpdateReadHistoryInbox(
                    peer=peer.to_tl(),
                    max_id=self.related_ids[0],
                    still_unread_count=self.related_ids[1],
                    pts=self.pts,
                    pts_count=1,
                )

            case UpdateType.DIALOG_PIN:
                if (peer := await models.Peer.get_or_none(owner=user, id=self.related_id)) is None \
                        or (dialog := await models.Dialog.get_or_none(peer=peer, visible=True)) is None:
                    return None

                ucc.add_peer(peer)

                return UpdateDialogPinned(
                    pinned=dialog.pinned_index is not None,
                    peer=DialogPeer(
                        peer=peer.to_tl(),
                    ),
                )

            case UpdateType.DIALOG_PIN_REORDER:
                dialogs = await models.Dialog.filter(
                    peer__owner=user, pinned_index__not_isnull=True, visible=True,
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
                peer = await models.Peer.get_or_none(id=self.related_id, owner=user)
                if peer is None:
                    return None

                ucc.add_peer(peer)

                draft = await models.MessageDraft.get_or_none(peer=peer)
                if isinstance(draft, models.MessageDraft):
                    draft = draft.to_tl()
                elif draft is None:
                    draft = DraftMessageEmpty()

                return UpdateDraftMessage(
                    peer=peer.to_tl(),
                    draft=draft,
                )

            case UpdateType.MESSAGE_PIN_UPDATE:
                message = await models.MessageRef.get_or_none(
                    id=self.related_id, peer__owner=user
                ).select_related("peer")
                if message is None:
                    return None

                ucc.add_message(message.content_id)

                return UpdatePinnedMessages(
                    pinned=message.pinned,
                    peer=message.peer.to_tl(),
                    messages=[message.id],
                    pts=self.pts,
                    pts_count=1,
                )

            case UpdateType.USER_UPDATE:
                if (peer := await models.Peer.from_user_id(user, self.related_id)) is None \
                        or (peer_user := peer.peer_user(user)) is None:
                    return None

                ucc.add_peer(peer)

                return UpdateUser(
                    user_id=peer_user.id,
                )

            case UpdateType.CHAT_CREATE:
                if (peer := await models.Peer.from_chat_id(user, self.related_id)) is None:
                    return None

                ucc.add_peer(peer)

                user_ids = set(self.related_ids)
                participants = []
                participant: models.ChatParticipant

                for participant in await models.ChatParticipant.filter(chat=peer.chat, user__id__in=self.related_ids):
                    participants.append(participant.to_tl_chat_with_creator(peer.chat.creator_id))
                    user_ids.remove(participant.user_id)

                for missing_id in user_ids:
                    if missing_id == peer.chat.creator_id:
                        participants.append(ChatParticipantCreator(user_id=missing_id))
                    else:
                        participants.append(ChatParticipant(
                            user_id=missing_id, inviter_id=peer.chat.creator_id, date=0,
                        ))

                return UpdateChatParticipants(
                    participants=ChatParticipants(
                        chat_id=peer.chat_id,
                        participants=participants,
                        version=1,
                    ),
                )

            case UpdateType.USER_UPDATE_NAME:
                if (peer := await models.Peer.from_user_id(user, self.related_id)) is None:
                    return None

                ucc.add_peer(peer)

                peer_user = peer.peer_user(user)
                user_username = await peer_user.get_username()
                return UpdateUserName(
                    user_id=peer_user.id,
                    first_name=peer_user.first_name,
                    last_name=peer_user.last_name,
                    usernames=[
                        Username(editable=True, active=True, username=user_username.username)
                    ] if user_username else [],
                )

            case UpdateType.UPDATE_CONTACT:
                if (contact := await models.Contact.get_or_none(owner=user, target__id=self.related_id)) is None:
                    return None

                ucc.add_user(contact.target_id)

                return UpdatePeerSettings(
                    peer=PeerUser(user_id=contact.target_id),
                    settings=PeerSettings(),
                )

            case UpdateType.UPDATE_BLOCK:
                if (peer := await models.Peer.from_user_id(user, self.related_id)) is None:
                    return None

                ucc.add_peer(peer)

                return UpdatePeerBlocked(
                    peer_id=peer.to_tl(),
                    blocked=peer.blocked_at is not None,
                )

            case UpdateType.UPDATE_CHAT:
                if (peer := await models.Peer.from_chat_id(user, self.related_id)) is None:
                    return None

                ucc.add_peer(peer)

                return UpdateChat(chat_id=peer.chat.id)

            case UpdateType.UPDATE_DIALOG_UNREAD_MARK:
                if (dialog := await models.Dialog.get_or_none(id=self.related_id).select_related("peer")) is None:
                    return None

                ucc.add_peer(dialog.peer)

                return UpdateDialogUnreadMark(
                    peer=DialogPeer(peer=dialog.peer.to_tl()),
                    unread=dialog.unread_mark,
                )

            case UpdateType.READ_INBOX:
                if not self.additional_data or len(self.additional_data) != 2:
                    return None
                if (peer := await models.Peer.get_or_none(owner=user, id=self.related_id)) is None:
                    return None

                ucc.add_peer(peer)

                if peer.type is PeerType.CHANNEL:
                    return UpdateReadChannelInbox(
                        channel_id=peer.channel_id,
                        max_id=self.additional_data[0],
                        still_unread_count=self.additional_data[1],
                        pts=self.pts,
                    )

                return UpdateReadHistoryInbox(
                    peer=peer.to_tl(),
                    max_id=self.additional_data[0],
                    still_unread_count=self.additional_data[1],
                    pts=self.pts,
                    pts_count=self.pts_count,
                )

            case UpdateType.READ_OUTBOX:
                if not self.additional_data or len(self.additional_data) != 1:
                    return None
                if (peer := await models.Peer.get_or_none(owner=user, id=self.related_id)) is None:
                    return None

                ucc.add_peer(peer)

                return UpdateReadHistoryOutbox(
                    peer=peer.to_tl(),
                    max_id=self.additional_data[0],
                    pts=self.pts,
                    pts_count=self.pts_count,
                )

            case UpdateType.FOLDER_PEERS:
                folder_peers = []

                dialog: models.Dialog
                async for dialog in models.Dialog.filter(
                        peer__id__in=self.related_ids, visible=True,
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
                        owner=user, id=self.related_id, id_for_user=folder_id_for_user,
                    )

                return UpdateDialogFilter(
                    id=folder_id_for_user,
                    filter=await folder.to_tl() if folder is not None else None,
                )

            case UpdateType.FOLDERS_ORDER:
                return UpdateDialogFilterOrder(order=self.related_ids)

            case UpdateType.UPDATE_ENCRYPTION:
                if auth_id is None:
                    return None

                if (chat := await models.EncryptedChat.get_or_none(id=self.related_id)) is None:
                    return None

                other_user_id = chat.from_user_id if user.id == chat.to_user_id else chat.to_user_id
                ucc.add_user(other_user_id)

                return UpdateEncryption(
                    chat=chat.to_tl(),
                    date=int(self.date.timestamp()),
                )

            case UpdateType.UPDATE_CONFIG:
                return UpdateConfig()

            case UpdateType.UPDATE_RECENT_REACTIONS:
                return UpdateRecentReactions()

            case UpdateType.NEW_AUTHORIZATION:
                if (auth := await models.UserAuthorization.get_or_none(id=self.related_id)) is None:
                    return None

                unconfirmed = not auth.confirmed
                return UpdateNewAuthorization(
                    unconfirmed=unconfirmed,
                    hash=auth.tl_hash,
                    date=int(auth.created_at.timestamp()) if unconfirmed else None,
                    device=auth.device_model if unconfirmed else None,
                    location=auth.ip if unconfirmed else None,
                )

            case UpdateType.NEW_STICKERSET:
                if (stickerset := await models.Stickerset.get_or_none(id=self.related_id, deleted=False)) is None:
                    return None

                return UpdateNewStickerSet(
                    stickerset=await stickerset.to_tl_messages(user),
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
                    wallpaper = await models.Wallpaper.get_or_none(id=self.related_ids[0]).select_related(
                        "document", "settings",
                    )
                    chat_wallpaper = await models.ChatWallpaper.get_or_none(user=user, wallpaper=wallpaper)
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
                message = await models.MessageRef.get_or_none(
                    id=self.related_id, content__type=MessageType.SCHEDULED, peer__owner=user
                ).select_related(*models.MessageRef.PREFETCH_FIELDS)
                if message is None:
                    return None

                ucc.add_message(message.content_id)

                return UpdateNewScheduledMessage(message=await message.to_tl(user))

            case UpdateType.DELETE_SCHEDULED_MESSAGE:
                if (peer := await models.Peer.get_or_none(owner=user, id=self.related_id)) is None:
                    return None

                deleted_message_ids = self.related_ids[:self.pts_count]
                sent_message_ids = self.related_ids[self.pts_count:]

                return UpdateDeleteScheduledMessages(
                    peer=peer.to_tl(),
                    messages=deleted_message_ids,
                    sent_messages=sent_message_ids or None,
                )

            case UpdateType.UPDATE_HISTORY_TTL:
                if (peer := await models.Peer.get_or_none(owner=user, id=self.related_id)) is None:
                    return None

                ttl_days = self.additional_data[0]
                return UpdatePeerHistoryTTL(
                    peer=peer.to_tl(),
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
                        user=user, peer__owner=user, peer__id=self.related_id,
                    ).select_related("peer")
                    if settings is not None and settings.peer is not None:
                        peer = settings.peer
                        ucc.add_peer(settings.peer)
                elif self.additional_data and self.additional_data[0] in NotifySettingsNotPeerType._value2member_map_:
                    settings = await models.PeerNotifySettings.get_or_none(
                        user=user, peer=None, not_peer=NotifySettingsNotPeerType(self.additional_data[0]),
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
                query = await models.InlineQuery.get_or_none(id=self.related_id, bot=user)
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
                    peer__owner=user, peer__id=self.related_id,
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
                    peer__owner=user, pinned_index__not_isnull=True,
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
                    user=user, id=self.related_id,
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
                call = await models.PhoneCall.get_or_none(Q(from_user=user) | Q(to_user=user), id=self.related_id)
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

        return None
