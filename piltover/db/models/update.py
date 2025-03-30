from __future__ import annotations

from datetime import datetime

from tortoise import fields, Model
from tortoise.expressions import Q

from piltover.db import models
from piltover.db.enums import UpdateType, PeerType
from piltover.tl import UpdateEditMessage, UpdateReadHistoryInbox, UpdateDialogPinned, DialogPeer, \
    UpdateDialogFilterOrder
from piltover.tl.types import UpdateDeleteMessages, UpdatePinnedDialogs, UpdateDraftMessage, DraftMessageEmpty, \
    UpdatePinnedMessages, UpdateUser, UpdateChatParticipants, ChatParticipants, ChatParticipantCreator, Username, \
    UpdateUserName, UpdatePeerSettings, PeerUser, PeerSettings, UpdatePeerBlocked, UpdateChat, UpdateDialogUnreadMark, \
    UpdateReadHistoryOutbox, ChatParticipant, UpdateFolderPeers, FolderPeer, UpdateChannel, UpdateReadChannelInbox, \
    UpdateMessagePoll, UpdateDialogFilter

UpdateTypes = UpdateDeleteMessages | UpdateEditMessage | UpdateReadHistoryInbox | UpdateDialogPinned \
              | UpdatePinnedDialogs | UpdateDraftMessage | UpdatePinnedMessages | UpdateUser | UpdateChatParticipants \
              | UpdateUserName | UpdatePeerSettings | UpdatePeerBlocked | UpdateChat | UpdateDialogUnreadMark \
              | UpdateReadHistoryOutbox | UpdateFolderPeers | UpdateChannel | UpdateReadChannelInbox \
              | UpdateMessagePoll | UpdateDialogFilter | UpdateDialogFilterOrder


class Update(Model):
    id: int = fields.BigIntField(pk=True)
    update_type: UpdateType = fields.IntEnumField(UpdateType)
    pts: int = fields.BigIntField()
    pts_count: int = fields.IntField(default=0)
    date: datetime = fields.DatetimeField(auto_now_add=True)
    related_id: int = fields.BigIntField(index=True, null=True)
    # TODO: probably there is a better way to store multiple updates (right now it is only used for deleted messages,
    #  so maybe create two tables: something like UpdateDeletedMessage and UpdateDeletedMessageId, related_id will point to
    #  UpdateDeletedMessage.id and UpdateDeletedMessage will have one-to-many relation to UpdateDeletedMessageId)
    related_ids: list[int] = fields.JSONField(null=True, default=None)
    additional_data: list | dict = fields.JSONField(null=True, default=None)
    user: models.User = fields.ForeignKeyField("models.User")

    async def to_tl(
            self, user: models.User, users_q: Q | None = None, chats_q: Q | None = None, channels_q: Q | None = None,
    ) -> tuple[UpdateTypes | None, Q | None, Q | None, Q | None]:
        none_ret = None, users_q, chats_q, channels_q

        match self.update_type:
            case UpdateType.MESSAGE_DELETE:
                return UpdateDeleteMessages(
                    messages=self.related_ids,
                    pts=self.pts,
                    pts_count=len(self.related_ids),
                ), users_q, chats_q, channels_q
            case UpdateType.MESSAGE_EDIT:
                if (message := await models.Message.get_or_none(id=self.related_id).select_related("peer", "author")) is None:
                    return none_ret

                users_q, chats_q, channels_q = message.query_users_chats(users_q, chats_q, channels_q)

                return UpdateEditMessage(
                    message=await message.to_tl(user),
                    pts=self.pts,
                    pts_count=1,
                ), users_q, chats_q, channels_q

            case UpdateType.READ_HISTORY_INBOX:
                query = Q(owner=user)
                if self.related_id:
                    query &= Q(user__id=self.related_id) | Q(chat__id=self.related_id)
                else:
                    query &= Q(type=PeerType.SELF)
                if (peer := await models.Peer.get_or_none(query)) is None:
                    return none_ret

                users_q, chats_q, channels_q = peer.query_users_chats(users_q, chats_q, channels_q)

                # TODO: fetch read state from db instead of related_ids
                return UpdateReadHistoryInbox(
                    peer=peer.to_tl(),
                    max_id=self.related_ids[0],
                    still_unread_count=self.related_ids[1],
                    pts=self.pts,
                    pts_count=1,
                ), users_q, chats_q, channels_q

            case UpdateType.DIALOG_PIN:
                if (peer := await models.Peer.get_or_none(owner=user, id=self.related_id)) is None \
                        or (dialog := await models.Dialog.get_or_none(peer=peer)) is None:
                    return none_ret

                users_q, chats_q, channels_q = peer.query_users_chats(users_q, chats_q, channels_q)

                return UpdateDialogPinned(
                    pinned=dialog.pinned_index is not None,
                    peer=DialogPeer(
                        peer=peer.to_tl(),
                    ),
                ), users_q, chats_q, channels_q

            case UpdateType.DIALOG_PIN_REORDER:
                dialogs = await models.Dialog.filter(
                    peer__owner=user, pinned_index__not_isnull=True
                ).select_related("peer")

                for dialog in dialogs:
                    users_q, chats_q, channels_q = dialog.peer.query_users_chats(users_q, chats_q, channels_q)

                return UpdatePinnedDialogs(
                    order=[
                        DialogPeer(peer=dialog.peer.to_tl())
                        for dialog in dialogs
                    ],
                ), users_q, chats_q, channels_q

            case UpdateType.DRAFT_UPDATE:
                peer = await models.Peer.get_or_none(id=self.related_id, owner=user)
                if peer is None:
                    return none_ret

                users_q, chats_q, channels_q = peer.query_users_chats(users_q, chats_q, channels_q)

                draft = await models.MessageDraft.get_or_none(dialog__peer=peer)
                if isinstance(draft, models.MessageDraft):
                    draft = draft.to_tl()
                elif draft is None:
                    draft = DraftMessageEmpty()

                return UpdateDraftMessage(
                    peer=peer.to_tl(),
                    draft=draft,
                ), users_q, chats_q, channels_q

            case UpdateType.MESSAGE_PIN_UPDATE:
                message = await models.Message.get_or_none(
                    id=self.related_id, peer__owner=user
                ).select_related("peer", "author")
                if message is None:
                    return none_ret

                users_q, chats_q, channels_q = message.query_users_chats(users_q, chats_q, channels_q)

                return UpdatePinnedMessages(
                    pinned=message.pinned,
                    peer=message.peer.to_tl(),
                    messages=[message.id],
                    pts=self.pts,
                    pts_count=1,
                ), users_q, chats_q, channels_q

            case UpdateType.USER_UPDATE:
                if (peer := await models.Peer.from_user_id(user, self.related_id)) is None \
                        or (peer_user := peer.peer_user(user)) is None:
                    return none_ret

                users_q, chats_q, channels_q = peer.query_users_chats(users_q, chats_q, channels_q)

                return UpdateUser(
                    user_id=peer_user.id,
                ), users_q, chats_q, channels_q

            case UpdateType.CHAT_CREATE:
                if (peer := await models.Peer.from_chat_id(user, self.related_id)) is None:
                    return none_ret

                users_q, chats_q, channels_q = peer.query_users_chats(users_q, chats_q, channels_q)
                peer.chat.creator = await peer.chat.creator

                user_ids = set(self.related_ids)
                participants = []
                participant: models.ChatParticipant

                async for participant in models.ChatParticipant.filter(chat=peer.chat, user__id__in=self.related_ids):
                    participant.chat = peer.chat
                    participants.append(await participant.to_tl())
                    user_ids.remove(participant.user_id)

                for missing_id in user_ids:
                    if missing_id == peer.chat.creator.id:
                        participants.append(ChatParticipantCreator(user_id=missing_id))
                    else:
                        participants.append(ChatParticipant(user_id=missing_id, inviter_id=peer.chat.creator.id, date=0))

                return UpdateChatParticipants(
                    participants=ChatParticipants(
                        chat_id=peer.chat.creator.id,
                        participants=participants,
                        version=1,
                    ),
                ), users_q, chats_q, channels_q

            case UpdateType.USER_UPDATE_NAME:
                if (peer := await models.Peer.from_user_id(user, self.related_id)) is None:
                    return none_ret

                users_q, chats_q, channels_q = peer.query_users_chats(users_q, chats_q, channels_q)

                peer_user = peer.peer_user(user)
                user_username = await peer_user.get_username()
                return UpdateUserName(
                    user_id=peer_user.id,
                    first_name=peer_user.first_name,
                    last_name=peer_user.last_name,
                    usernames=[
                        Username(editable=True, active=True, username=user_username.username)
                    ] if user_username else [],
                ), users_q, chats_q, channels_q

            case UpdateType.UPDATE_CONTACT:
                if (contact := await models.Contact.get_or_none(owner=user, target__id=self.related_id)) is None:
                    return none_ret

                users_q, chats_q, channels_q = contact.query_users_chats(users_q, chats_q, channels_q)

                return UpdatePeerSettings(
                    peer=PeerUser(user_id=contact.target.id),
                    settings=PeerSettings(),
                ), users_q, chats_q, channels_q

            case UpdateType.UPDATE_BLOCK:
                if (peer := await models.Peer.from_user_id(user, self.related_id)) is None:
                    return none_ret

                users_q, chats_q, channels_q = peer.query_users_chats(users_q, chats_q, channels_q)

                return UpdatePeerBlocked(
                    peer_id=peer.to_tl(),
                    blocked=peer.blocked,
                ), users_q, chats_q, channels_q

            case UpdateType.UPDATE_CHAT:
                if (peer := await models.Peer.from_chat_id(user, self.related_id)) is None:
                    return none_ret

                users_q, chats_q, channels_q = peer.query_users_chats(users_q, chats_q, channels_q)

                return UpdateChat(chat_id=peer.chat.id), users_q, chats_q, channels_q

            case UpdateType.UPDATE_DIALOG_UNREAD_MARK:
                if (dialog := await models.Dialog.get_or_none(id=self.related_id).select_related("peer")) is None:
                    return none_ret

                users_q, chats_q, channels_q = dialog.peer.query_users_chats(users_q, chats_q, channels_q)

                return UpdateDialogUnreadMark(
                    peer=DialogPeer(peer=dialog.peer.to_tl()),
                    unread=dialog.unread_mark,
                ), users_q, chats_q, channels_q

            case UpdateType.READ_INBOX:
                if not self.additional_data or len(self.additional_data) != 2:
                    return none_ret
                if (peer := await models.Peer.get_or_none(owner=user, id=self.related_id)) is None:
                    return none_ret

                users_q, chats_q, channels_q = peer.query_users_chats(users_q, chats_q, channels_q)

                if peer.type is PeerType.CHANNEL:
                    return UpdateReadChannelInbox(
                        channel_id=peer.channel_id,
                        max_id=self.additional_data[0],
                        still_unread_count=self.additional_data[1],
                        pts=self.pts,
                    ), users_q, chats_q, channels_q

                return UpdateReadHistoryInbox(
                    peer=peer.to_tl(),
                    max_id=self.additional_data[0],
                    still_unread_count=self.additional_data[1],
                    pts=self.pts,
                    pts_count=self.pts_count,
                ), users_q, chats_q, channels_q

            case UpdateType.READ_OUTBOX:
                if not self.additional_data or len(self.additional_data) != 1:
                    return none_ret
                if (peer := await models.Peer.get_or_none(owner=user, id=self.related_id)) is None:
                    return none_ret

                users_q, chats_q, channels_q = peer.query_users_chats(users_q, chats_q, channels_q)

                return UpdateReadHistoryOutbox(
                    peer=peer.to_tl(),
                    max_id=self.additional_data[0],
                    pts=self.pts,
                    pts_count=self.pts_count,
                ), users_q, chats_q, channels_q

            case UpdateType.FOLDER_PEERS:
                folder_peers = []
                users_q, chats_q, channels_q = Q(), Q(), Q()

                dialog: models.Dialog
                async for dialog in models.Dialog.filter(peer__id__in=self.related_ids).select_related("peer"):
                    folder_peers.append(FolderPeer(peer=dialog.peer.to_tl(), folder_id=dialog.folder_id.value))
                    users_q, chats_q, channels_q = dialog.peer.query_users_chats(users_q, chats_q, channels_q)

                return UpdateFolderPeers(
                    folder_peers=folder_peers,
                    pts=self.pts,
                    pts_count=self.pts_count,
                ), users_q, chats_q, channels_q

            case UpdateType.UPDATE_CHANNEL:
                channels_q |= Q(id=self.related_id)
                return UpdateChannel(
                    channel_id=self.related_id,
                ), users_q, chats_q, channels_q

            case UpdateType.UPDATE_POLL:
                if (poll := await models.Poll.get_or_none(id=self.related_id)) is None:
                    return none_ret

                return UpdateMessagePoll(
                    poll_id=poll.id,
                    poll=await poll.to_tl(),
                    results=await poll.to_tl_results(user),
                ), users_q, chats_q, channels_q

            case UpdateType.UPDATE_FOLDER:
                folder_id_for_user = self.related_ids[0]
                folder = await models.DialogFolder.get_or_none(
                    owner=user, id=self.related_id, id_for_user=folder_id_for_user,
                )

                return UpdateDialogFilter(
                    id=folder_id_for_user,
                    filter=await folder.to_tl() if folder is not None else None,
                ), users_q, chats_q, channels_q

            case UpdateType.FOLDERS_ORDER:
                return UpdateDialogFilterOrder(order=self.related_ids), users_q, chats_q, channels_q

        return None, users_q, chats_q, channels_q
