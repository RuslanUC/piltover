from __future__ import annotations

from datetime import datetime

from tortoise import fields

from piltover.db import models
from piltover.db.enums import UpdateType
from piltover.db.models._utils import Model
from piltover.tl import TLObject, UpdateEditMessage, UpdateReadHistoryInbox, UpdateDialogPinned, DialogPeer
from piltover.tl.types import UpdateDeleteMessages
from piltover.tl.types import User as TLUser


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
    # TODO?: for supergroups/channels
    #parent_chat: models.Chat = fields.ForeignKeyField("models.Chat", null=True, default=None)

    async def to_tl(self, current_user: models.User, users: dict[int, TLUser] | None = None) -> TLObject | None:
        if self.update_type == UpdateType.MESSAGE_DELETE:
            return UpdateDeleteMessages(
                messages=self.related_ids,
                pts=self.pts,
                pts_count=len(self.related_ids),
            )

        if self.update_type == UpdateType.MESSAGE_EDIT:
            if (message := await models.Message.get_or_none(id=self.related_id).select_related("chat", "author")) is None:
                return

            if users is not None and message.author.id not in users:
                users[message.author.id] = await message.author.to_tl(current_user)

            return UpdateEditMessage(
                message=await message.to_tl(current_user),
                pts=self.pts,
                pts_count=1,
            )

        if self.update_type == UpdateType.READ_HISTORY_INBOX:
            if (chat := await models.Chat.get_or_none(id=self.related_id)) is None:
                return

            # TODO: fetch read state from db instead of related_ids
            return UpdateReadHistoryInbox(
                peer=await chat.get_peer(current_user),
                max_id=self.related_ids[0],
                still_unread_count=self.related_ids[1],
                pts=self.pts,
                pts_count=1,
            )

        if self.update_type == UpdateType.DIALOG_PIN:
            if (chat := await models.Chat.get_or_none(id=self.related_id)) is None \
                    or (dialog := await models.Dialog.get_or_none(chat=chat, user=current_user)) is None:
                return

            if users is not None \
                    and (other := await chat.get_other_user(current_user)) is not None \
                    and other.id not in users:
                users[other.id] = other

            return UpdateDialogPinned(
                pinned=dialog.pinned_index is not None,
                peer=DialogPeer(
                    peer=await chat.get_peer(current_user),
                ),
            )
