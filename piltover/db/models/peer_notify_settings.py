from __future__ import annotations

from datetime import datetime

from tortoise import fields, Model

from piltover.db import models
from piltover.tl.types import PeerNotifySettings as TLPeerNotifySettings


class PeerNotifySettings(Model):
    id: int = fields.BigIntField(pk=True)
    peer: models.Peer = fields.OneToOneField("models.Peer")
    show_previews: bool = fields.BooleanField(default=True)
    muted: bool = fields.BooleanField(default=False)
    muted_until: datetime = fields.DatetimeField(null=True, default=None)

    def to_tl(self) -> TLPeerNotifySettings:
        return TLPeerNotifySettings(
            show_previews=self.show_previews,
            silent=self.muted,
            mute_until=int(self.muted_until.timestamp()) if self.muted_until else None,
            android_sound=None,  # TODO
            other_sound=None,  # TODO
            ios_sound=None,
            stories_muted=True,
            stories_hide_sender=True,
            stories_android_sound=None,
            stories_ios_sound=None,
            stories_other_sound=None,
        )
