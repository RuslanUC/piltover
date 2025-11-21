from __future__ import annotations

from datetime import datetime
from typing import overload

from tortoise import fields, Model

from piltover.db import models
from piltover.db.enums import NotifySettingsNotPeerType
from piltover.exceptions import Unreachable, ErrorRpc
from piltover.tl.base import NotifyPeer as BaseNotifyPeer, InputNotifyPeer as BaseInputNotifyPeer
from piltover.tl.types import PeerNotifySettings as TLPeerNotifySettings, NotifyPeer, NotifyUsers, NotifyChats, \
    NotifyBroadcasts, InputNotifyPeer, InputNotifyUsers, InputNotifyChats, InputNotifyBroadcasts


class PeerNotifySettings(Model):
    id: int = fields.BigIntField(pk=True)
    user: models.User = fields.ForeignKeyField("models.User")
    peer: models.Peer = fields.ForeignKeyField("models.Peer", null=True, default=None)
    not_peer: NotifySettingsNotPeerType = fields.IntEnumField(NotifySettingsNotPeerType, null=True, default=None)
    show_previews: bool = fields.BooleanField(default=True)
    muted: bool = fields.BooleanField(default=False)
    muted_until: datetime = fields.DatetimeField(null=True, default=None)

    class Meta:
        unique_together = (
            ("user", "peer"),
            ("user", "not_peer"),
        )

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

    @staticmethod
    def peer_to_tl(peer: models.Peer | None, not_peer: NotifySettingsNotPeerType | None) -> BaseNotifyPeer:
        if peer is not None:
            return NotifyPeer(peer=peer.to_tl())
        if not_peer is NotifySettingsNotPeerType.USERS:
            return NotifyUsers()
        if not_peer is NotifySettingsNotPeerType.CHATS:
            return NotifyChats()
        if not_peer is NotifySettingsNotPeerType.CHANNELS:
            return NotifyBroadcasts()

        raise Unreachable

    @staticmethod
    @overload
    async def peer_from_tl(
            user: models.User, notify_peer: BaseInputNotifyPeer,
    ) -> tuple[models.Peer | None, NotifySettingsNotPeerType | None]:
        ...

    @staticmethod
    @overload
    async def peer_from_tl(user: models.User, notify_peer: InputNotifyPeer) -> tuple[models.Peer, None]:
        ...

    @staticmethod
    @overload
    async def peer_from_tl(
            user: models.User, notify_peer: InputNotifyUsers | InputNotifyChats | InputNotifyBroadcasts,
    ) -> tuple[None, NotifySettingsNotPeerType]:
        ...

    @staticmethod
    async def peer_from_tl(
            user: models.User, notify_peer: BaseInputNotifyPeer,
    ) -> tuple[models.Peer | None, NotifySettingsNotPeerType | None]:
        if isinstance(notify_peer, InputNotifyPeer):
            peer = await models.Peer.from_input_peer_raise(user, notify_peer.peer)
            return peer, None
        elif isinstance(notify_peer, InputNotifyUsers):
            return None, NotifySettingsNotPeerType.USERS
        elif isinstance(notify_peer, InputNotifyChats):
            return None, NotifySettingsNotPeerType.CHATS
        elif isinstance(notify_peer, InputNotifyBroadcasts):
            return None, NotifySettingsNotPeerType.CHANNELS
        else:
            raise ErrorRpc(error_code=400, error_message="PEER_ID_NOT_SUPPORTED")
