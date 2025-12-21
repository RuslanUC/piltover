from __future__ import annotations

from datetime import datetime

from tortoise import Model, fields

from piltover.db import models
from piltover.db.enums import AdminLogEntryAction
from piltover.tl import ChannelAdminLogEventActionChangeTitle, ChannelAdminLogEventActionChangeAbout, \
    ChannelAdminLogEventActionChangeUsername, ChannelAdminLogEventActionToggleSignatures, \
    ChannelAdminLogEventActionChangePhoto, PhotoEmpty
from piltover.tl.base import ChannelAdminLogEvent


class AdminLogEntry(Model):
    id: int = fields.BigIntField(pk=True)
    user: models.User = fields.ForeignKeyField("models.User")
    channel: models.Channel = fields.ForeignKeyField("models.Channel")
    action: AdminLogEntryAction = fields.IntEnumField(AdminLogEntryAction)
    date: datetime = fields.DatetimeField(auto_now_add=True)

    prev: bytes = fields.BinaryField(null=True, default=None)
    old_photo: models.File | None = fields.ForeignKeyField("models.File", null=True, default=None, related_name="old_photo")

    new: bytes = fields.BinaryField(null=True, default=None)
    new_photo: models.File | None = fields.ForeignKeyField("models.File", null=True, default=None, related_name="new_photo")

    user_id: int
    channel_id: int
    old_photo_id: int | None
    new_photo_id: int | None

    def to_tl(self) -> ChannelAdminLogEvent | None:
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

        if action is None:
            return None

        return ChannelAdminLogEvent(
            id=self.id,
            date=int(self.date.timestamp()),
            user_id=self.user_id,
            action=action,
        )

    # TODO: add ability to search
