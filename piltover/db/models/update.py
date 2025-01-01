from __future__ import annotations

from datetime import datetime

from tortoise import fields

from piltover.db import models
from piltover.db.enums import UpdateType, PeerType
from piltover.db.models import Dialog
from piltover.db.models._utils import Model
from piltover.tl import UpdateEditMessage, UpdateReadHistoryInbox, UpdateDialogPinned, DialogPeer
from piltover.tl.types import UpdateDeleteMessages, UpdatePinnedDialogs, UpdateDraftMessage, DraftMessageEmpty, \
    UpdatePinnedMessages, UpdateUser, UpdateChatParticipants, ChatParticipants, ChatParticipantCreator
from piltover.tl.types import User as TLUser, Chat as TLChat

UpdateTypes = UpdateDeleteMessages | UpdateEditMessage | UpdateReadHistoryInbox | UpdateDialogPinned | \
              UpdatePinnedDialogs | UpdateDraftMessage | UpdatePinnedMessages | UpdateUser | UpdateChatParticipants


class UpdateV2(Model):
    id: int = fields.BigIntField(pk=True)
    update_type: UpdateType = fields.IntEnumField(UpdateType)
    pts: int = fields.BigIntField()
    date: datetime = fields.DatetimeField(auto_now_add=True)
    related_id: int = fields.BigIntField(index=True, null=True)
    # TODO: probably there is a better way to store multiple updates (right now it is only used for deleted messages,
    #  so maybe create two tables: something like UpdateDeletedMessage and UpdateDeletedMessageId, related_id will point to
    #  UpdateDeletedMessage.id and UpdateDeletedMessage will have one-to-many relation to UpdateDeletedMessageId)
    related_ids: list[int] = fields.JSONField(null=True, default=None)
    user: models.User = fields.ForeignKeyField("models.User")

    async def to_tl(
            self, current_user: models.User, users: dict[int, TLUser] | None = None,
            chats: dict[int, TLChat] | None = None,
    ) -> UpdateTypes | None:
        if self.update_type == UpdateType.MESSAGE_DELETE:
            return UpdateDeleteMessages(
                messages=self.related_ids,
                pts=self.pts,
                pts_count=len(self.related_ids),
            )

        if self.update_type == UpdateType.MESSAGE_EDIT:
            if (message := await models.Message.get_or_none(id=self.related_id).select_related("peer", "author")) is None:
                return

            if users is not None and message.author.id not in users:
                users[message.author.id] = await message.author.to_tl(current_user)
            if chats is not None and message.peer.type is PeerType.CHAT and message.peer.chat_id not in chats:
                await message.peer.fetch_related("chat")
                chats[message.peer.chat.id] = await message.peer.chat.to_tl(current_user)

            return UpdateEditMessage(
                message=await message.to_tl(current_user),
                pts=self.pts,
                pts_count=1,
            )

        if self.update_type == UpdateType.READ_HISTORY_INBOX:
            query = {"user__id": self.related_id} if self.related_id else {"type": PeerType.SELF}
            if (peer := await models.Peer.get_or_none(owner=current_user, **query)) is None:
                return

            # TODO: fetch read state from db instead of related_ids
            return UpdateReadHistoryInbox(
                peer=peer.to_tl(),
                max_id=self.related_ids[0],
                still_unread_count=self.related_ids[1],
                pts=self.pts,
                pts_count=1,
            )

        if self.update_type == UpdateType.DIALOG_PIN:
            if (peer := await models.Peer.get_or_none(owner=current_user, id=self.related_id)) is None \
                    or (dialog := await models.Dialog.get_or_none(peer=peer)) is None:
                return

            if users is not None and (other := await peer.get_opposite()) is not None:
                for opp in other:
                    if opp.user.id not in users:
                        users[opp.user.id] = opp.user

            if chats is not None and peer.type is PeerType.CHAT and peer.chat_id not in chats:
                chat = await peer.chat
                chats[peer.chat_id] = await chat.to_tl(current_user)

            return UpdateDialogPinned(
                pinned=dialog.pinned_index is not None,
                peer=DialogPeer(
                    peer=peer.to_tl(),
                ),
            )

        if self.update_type is UpdateType.DIALOG_PIN_REORDER:
            dialogs = await Dialog.filter(
                peer__owner=current_user, pinned_index__not_isnull=True
            ).select_related("peer", "peer__user")

            for dialog in dialogs:
                peer = dialog.peer
                peer_user = peer.peer_user(current_user)
                if users is not None and peer_user.id not in users:
                    users[peer_user.id] = peer_user
                if chats is not None and peer.type is PeerType.CHAT and peer.chat_id not in chats:
                    chat = await peer.chat
                    chats[peer.chat_id] = await chat.to_tl(current_user)

            return UpdatePinnedDialogs(
                order=[
                    DialogPeer(peer=dialog.peer.to_tl())
                    for dialog in dialogs
                ],
            )

        if self.update_type is UpdateType.DRAFT_UPDATE:
            peer = await models.Peer.get_or_none(id=self.related_id, owner=current_user).select_related("user")
            if peer is None:
                return

            if users is not None and peer.user is not None and peer.user.id not in users:
                users[peer.user.id] = peer.user
            if chats is not None and peer.type is PeerType.CHAT and peer.chat_id not in chats:
                await peer.fetch_related("chat")
                chats[peer.chat.id] = await peer.chat.to_tl(current_user)

            draft = await models.MessageDraft.get_or_none(dialog__peer=peer)
            if isinstance(draft, models.MessageDraft):
                draft = draft.to_tl()
            elif draft is None:
                draft = DraftMessageEmpty()

            return UpdateDraftMessage(
                peer=peer.to_tl(),
                draft=draft,
            )

        if self.update_type is UpdateType.MESSAGE_PIN_UPDATE:
            message = await models.Message.get_or_none(
                id=self.related_id, peer__owner=current_user
            ).select_related("peer", "author")
            if message is None:
                return

            if users is not None and message.peer.user is not None and message.peer.user.id not in users:
                users[message.peer.user.id] = message.peer.user
            if users is not None and message.author.id not in users:
                users[message.author.id] = message.author
            if chats is not None and message.peer.type is PeerType.CHAT and message.peer.chat_id not in chats:
                await message.peer.fetch_related("chat")
                chats[message.peer.chat.id] = await message.peer.chat.to_tl(current_user)

            return UpdatePinnedMessages(
                pinned=message.pinned,
                peer=message.peer.to_tl(),
                messages=[message.id],
                pts=self.pts,
                pts_count=1,
            )

        if self.update_type is UpdateType.USER_UPDATE:
            if (peer := await models.Peer.from_user_id(current_user, self.related_id)) is None \
                    or (peer_user := peer.peer_user(current_user)) is None:
                return

            if users is not None and peer_user.id not in users:
                users[peer_user.id] = peer_user

            return UpdateUser(
                user_id=peer_user.id,
            )

        if self.update_type is UpdateType.CHAT_CREATE:
            if (peer := await models.Peer.from_chat_id(current_user, self.related_id)) is None:
                return

            await peer.chat.fetch_related("creator")
            if peer.chat.creator.id not in users:
                users[peer.chat.creator.id] = peer.chat.creator
            if chats is not None and peer.chat_id not in chats:
                chats[peer.chat.id] = await peer.chat.to_tl(current_user)

            return UpdateChatParticipants(
                participants=ChatParticipants(
                    chat_id=peer.chat.creator.id,
                    participants=[
                        ChatParticipantCreator(user_id=peer.chat.creator.id)
                    ],
                    version=1,
                ),
            )
