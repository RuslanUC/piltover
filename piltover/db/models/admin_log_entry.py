from __future__ import annotations

from datetime import datetime
from io import BytesIO

from tortoise import Model, fields

from piltover.db import models
from piltover.db.enums import AdminLogEntryAction, ChatBannedRights
from piltover.db.models.utils import IntFlagField
from piltover.exceptions import InvalidConstructorException, Unreachable
from piltover.tl import ChannelAdminLogEventActionChangeTitle, ChannelAdminLogEventActionChangeAbout, \
    ChannelAdminLogEventActionChangeUsername, ChannelAdminLogEventActionToggleSignatures, \
    ChannelAdminLogEventActionChangePhoto, PhotoEmpty, ChannelAdminLogEventActionParticipantJoin, \
    ChannelAdminLogEventActionParticipantLeave, ChannelAdminLogEventActionToggleNoForwards, \
    ChannelAdminLogEventActionDefaultBannedRights, ChannelAdminLogEventActionTogglePreHistoryHidden, PeerColor, \
    ChannelAdminLogEventActionChangePeerColor, ChannelAdminLogEventActionChangeProfilePeerColor, \
    ChannelAdminLogEventActionChangeLinkedChat, ChannelAdminLogEventActionChangeHistoryTTL, Int, \
    ChannelAdminLogEventActionToggleSlowMode, TLObject, ChannelAdminLogEventActionParticipantToggleAdmin, \
    ChannelParticipantBanned, ChannelParticipantAdmin, ChannelParticipantCreator, ChannelParticipant, \
    ChannelParticipantLeft, ChannelParticipantSelf, ChannelParticipantSelf_133, ChannelParticipantSelf_134, \
    ChannelParticipant_133, ChannelAdminLogEventActionParticipantToggleBan
from piltover.tl.base import ChannelAdminLogEvent, ChannelParticipantInst, ChannelParticipant as ChannelParticipantBase
from piltover.utils.users_chats_channels import UsersChatsChannels


ParticipantWithUserId = (
    ChannelParticipantCreator, ChannelParticipant, ChannelParticipant_133, ChannelParticipantSelf,
    ChannelParticipantSelf_133, ChannelParticipantSelf_134, ChannelParticipantAdmin,
)
ParticipantWithUserPeer = (
    ChannelParticipantBanned, ChannelParticipantLeft,
)


def _add_participant_to_ucc(participant: ChannelParticipantBase, ucc: UsersChatsChannels) -> None:
    if isinstance(participant, ParticipantWithUserId):
        ucc.add_user(participant.user_id)
    elif isinstance(participant, ParticipantWithUserPeer):
        ucc.add_user(participant.peer.user_id)
    else:
        raise Unreachable

    if isinstance(participant, ChannelParticipantBanned):
        if participant.kicked_by:
            ucc.add_user(participant.kicked_by)
    elif isinstance(participant, ChannelParticipantAdmin):
        if participant.promoted_by:
            ucc.add_user(participant.promoted_by)
    elif isinstance(participant, (ChannelParticipantSelf, ChannelParticipantSelf_133, ChannelParticipantSelf_134)):
        if participant.inviter_id:
            ucc.add_user(participant.inviter_id)


def _process_channel_participant(
        prev_bytes: bytes | None, new_bytes: bytes | None, ucc: UsersChatsChannels,
) -> tuple[ChannelParticipantBase, ChannelParticipantBase] | None:
    if not prev_bytes or not new_bytes:
        return None

    try:
        prev: ChannelParticipantBase = TLObject.read(BytesIO(prev_bytes))
        new: ChannelParticipantBase = TLObject.read(BytesIO(new_bytes))
    except InvalidConstructorException:
        return None

    if not isinstance(prev, ChannelParticipantInst) or not isinstance(new, ChannelParticipantInst):
        return None

    _add_participant_to_ucc(prev, ucc)
    _add_participant_to_ucc(new, ucc)

    return prev, new


class AdminLogEntry(Model):
    id: int = fields.BigIntField(pk=True)
    user: models.User = fields.ForeignKeyField("models.User")
    channel: models.Channel = fields.ForeignKeyField("models.Channel")
    action: AdminLogEntryAction = fields.IntEnumField(AdminLogEntryAction)
    date: datetime = fields.DatetimeField(auto_now_add=True)

    prev: bytes = fields.BinaryField(null=True, default=None)
    old_photo: models.File | None = fields.ForeignKeyField("models.File", null=True, default=None, related_name="old_photo")
    old_banned_rights: ChatBannedRights | None = IntFlagField(ChatBannedRights, null=True, default=None)
    old_channel: models.Channel | None = fields.ForeignKeyField("models.Channel", null=True, default=None, related_name="old_channel")

    new: bytes = fields.BinaryField(null=True, default=None)
    new_photo: models.File | None = fields.ForeignKeyField("models.File", null=True, default=None, related_name="new_photo")
    new_banned_rights: ChatBannedRights | None = IntFlagField(ChatBannedRights, null=True, default=None)
    new_channel: models.Channel | None = fields.ForeignKeyField("models.Channel", null=True, default=None, related_name="new_channel")

    user_id: int
    channel_id: int
    old_photo_id: int | None
    new_photo_id: int | None
    old_channel_id: int | None
    new_channel_id: int | None

    def to_tl(self, ucc: UsersChatsChannels) -> ChannelAdminLogEvent | None:
        action = None
        if self.action is AdminLogEntryAction.CHANGE_TITLE:
            action = ChannelAdminLogEventActionChangeTitle(
                prev_value=self.prev.decode("utf8"),
                new_value=self.new.decode("utf8"),
            )
        elif self.action is AdminLogEntryAction.CHANGE_ABOUT:
            action = ChannelAdminLogEventActionChangeAbout(
                prev_value=self.prev.decode("utf8"),
                new_value=self.new.decode("utf8"),
            )
        elif self.action is AdminLogEntryAction.CHANGE_USERNAME:
            action = ChannelAdminLogEventActionChangeUsername(
                prev_value=self.prev.decode("utf8"),
                new_value=self.new.decode("utf8"),
            )
        elif self.action is AdminLogEntryAction.TOGGLE_SIGNATURES:
            action = ChannelAdminLogEventActionToggleSignatures(
                new_value=self.new == b"\x01",
            )
        elif self.action is AdminLogEntryAction.CHANGE_PHOTO:
            action = ChannelAdminLogEventActionChangePhoto(
                prev_photo=self.old_photo.to_tl_photo() if self.old_photo_id else PhotoEmpty(id=0),
                new_photo=self.new_photo.to_tl_photo() if self.new_photo_id else PhotoEmpty(id=0),
            )
        elif self.action is AdminLogEntryAction.PARTICIPANT_JOIN:
            action = ChannelAdminLogEventActionParticipantJoin()
        elif self.action is AdminLogEntryAction.PARTICIPANT_LEAVE:
            action = ChannelAdminLogEventActionParticipantLeave()
        elif self.action is AdminLogEntryAction.TOGGLE_NOFORWARDS:
            action = ChannelAdminLogEventActionToggleNoForwards(
                new_value=self.new == b"\x01",
            )
        elif self.action is AdminLogEntryAction.DEFAULT_BANNED_RIGHTS:
            action = ChannelAdminLogEventActionDefaultBannedRights(
                prev_banned_rights=self.old_banned_rights.to_tl(),
                new_banned_rights=self.new_banned_rights.to_tl(),
            )
        elif self.action is AdminLogEntryAction.PREHISTORY_HIDDEN:
            action = ChannelAdminLogEventActionTogglePreHistoryHidden(
                new_value=self.new == b"\x01",
            )
        elif self.action is AdminLogEntryAction.EDIT_PEER_COLOR:
            action = ChannelAdminLogEventActionChangePeerColor(
                prev_value=PeerColor.deserialize(BytesIO(self.prev)),
                new_value=PeerColor.deserialize(BytesIO(self.new)),
            )
        elif self.action is AdminLogEntryAction.EDIT_PEER_COLOR_PROFILE:
            action = ChannelAdminLogEventActionChangeProfilePeerColor(
                prev_value=PeerColor.deserialize(BytesIO(self.prev)),
                new_value=PeerColor.deserialize(BytesIO(self.new)),
            )
        elif self.action is AdminLogEntryAction.EDIT_PEER_COLOR_PROFILE:
            action = ChannelAdminLogEventActionChangeLinkedChat(
                prev_value=self.old_channel_id or 0,
                new_value=self.new_channel_id or 0,
            )
        elif self.action is AdminLogEntryAction.EDIT_HISTORY_TTL:
            action = ChannelAdminLogEventActionChangeHistoryTTL(
                prev_value=Int.read_bytes(self.prev),
                new_value=Int.read_bytes(self.new),
            )
        elif self.action is AdminLogEntryAction.TOGGLE_SLOWMODE:
            action = ChannelAdminLogEventActionToggleSlowMode(
                prev_value=Int.read_bytes(self.prev),
                new_value=Int.read_bytes(self.new),
            )
        elif self.action is AdminLogEntryAction.PARTICIPANT_ADMIN:
            participant = _process_channel_participant(self.prev, self.new, ucc)
            if participant is None:
                return None

            prev, new = participant
            action = ChannelAdminLogEventActionParticipantToggleAdmin(
                prev_participant=prev,
                new_participant=new,
            )
        elif self.action is AdminLogEntryAction.PARTICIPANT_BAN:
            participant = _process_channel_participant(self.prev, self.new, ucc)
            if participant is None:
                return None

            prev, new = participant
            action = ChannelAdminLogEventActionParticipantToggleBan(
                prev_participant=prev,
                new_participant=new,
            )

        if action is None:
            return None

        ucc.add_user(self.user_id)
        if self.old_channel_id is not None:
            ucc.add_channel(self.old_channel_id)
        if self.new_channel_id is not None:
            ucc.add_channel(self.new_channel_id)

        return ChannelAdminLogEvent(
            id=self.id,
            date=int(self.date.timestamp()),
            user_id=self.user_id,
            action=action,
        )

    # TODO: add ability to search
