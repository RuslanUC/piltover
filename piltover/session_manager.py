from __future__ import annotations

from dataclasses import dataclass, field
from time import time
from typing import TYPE_CHECKING

from loguru import logger
from mtproto.packets import DecryptedMessagePacket

from piltover.db.models import UserAuthorization, AuthKey, Channel
from piltover.layer_converter.manager import LayerConverter
from piltover.tl import TLObject, Updates
from piltover.tl.core_types import Message, MsgContainer
from piltover.tl.types.internal import MessageToUsersShort, ChannelSubscribe, ChannelToFetch
from piltover.tl.utils import is_content_related

if TYPE_CHECKING:
    from piltover.gateway import Client
    from piltover.message_brokers.base_broker import BaseMessageBroker


@dataclass(slots=True)
class KeyInfo:
    auth_key: bytes
    auth_key_id: int


@dataclass
class Session:
    # TODO: store sessions in redis or something (with non-acked messages) to be able to restore session after reconnect

    client: Client | None
    session_id: int
    auth_key: KeyInfo | None = None
    user_id: int | None = None
    channel_ids: list[int] = field(default_factory=list)
    min_msg_id: int = 0
    online: bool = False

    msg_id_last_time = 0
    msg_id_offset = 0
    incoming_content_related_msgs = 0
    outgoing_content_related_msgs = 0

    def msg_id(self, in_reply: bool) -> int:
        # Client message identifiers are divisible by 4, server message
        # identifiers modulo 4 yield 1 if the message is a response to
        # a client message, and 3 otherwise.

        now = int(time())
        self.msg_id_offset = (self.msg_id_offset + 4) if now == self.msg_id_last_time else 0
        msg_id = (now * 2 ** 32) + self.msg_id_offset + (1 if in_reply else 3)
        self.msg_id_last_time = now

        assert msg_id % 4 in [1, 3], f"Invalid server msg_id: {msg_id}"
        return msg_id

    def update_incoming_content_related_msgs(self, obj: TLObject, seq_no: int):
        expected = self.incoming_content_related_msgs * 2
        if is_content_related(obj):
            self.incoming_content_related_msgs += 1
            expected += 1

    def get_outgoing_seq_no(self, obj: TLObject) -> int:
        ret = self.outgoing_content_related_msgs * 2
        if is_content_related(obj):
            self.outgoing_content_related_msgs += 1
            ret += 1
        return ret

    # https://core.telegram.org/mtproto/description#message-identifier-msg-id
    def pack_message(
            self, obj: TLObject, originating_request: Message | DecryptedMessagePacket | None = None
    ) -> Message:
        if originating_request is None:
            msg_id = self.msg_id(in_reply=False)
        else:
            if is_content_related(obj):
                msg_id = self.msg_id(in_reply=True)
            else:
                msg_id = originating_request.message_id + 1

        return Message(
            message_id=msg_id,
            seq_no=self.get_outgoing_seq_no(obj),
            obj=LayerConverter.downgrade(obj, self.client.layer)
        )

    # https://core.telegram.org/mtproto/description#message-identifier-msg-id
    def pack_container(self, objects: list[tuple[TLObject, Message]]) -> Message:
        container = MsgContainer(messages=[])
        for obj, originating_request in objects:
            if is_content_related(obj):
                msg_id = self.msg_id(in_reply=True)
            else:
                msg_id = originating_request.message_id + 1
            seq_no = self.get_outgoing_seq_no(obj)

            container.messages.append(Message(message_id=msg_id, seq_no=seq_no, obj=obj))

        return self.pack_message(container)

    def __hash__(self) -> int:
        return self.session_id

    def set_user_id(self, user_id: int) -> None:
        self.user_id = user_id
        self.online = True

        SessionManager.broker.subscribe(self)

    def destroy(self) -> None:
        self.online = False
        SessionManager.broker.unsubscribe(self)
        SessionManager.cleanup(self)

    async def send(self, obj: TLObject) -> None:
        if not self.online:
            return

        if isinstance(obj, Updates):
            key = await AuthKey.get_or_temp(self.auth_key.auth_key_id)
            auth = await UserAuthorization.get(key__id=str(key.id if isinstance(key, AuthKey) else key.perm_key.id))
            auth.upd_seq += 1
            await auth.save(update_fields=["upd_seq"])
            obj.seq = auth.upd_seq

            for idx, chat_or_channel in enumerate(obj.chats):
                if isinstance(chat_or_channel, ChannelToFetch):
                    channel = await Channel.get_or_none(id=chat_or_channel.channel_id)
                    obj.chats[idx] = await channel.to_tl(self.user_id)

        try:
            await self.client.send(obj, self)
        except Exception as e:
            logger.opt(exception=e).warning(f"Failed to send {obj} to {self.client}")


class SessionManager:
    sessions: dict[int, dict[int, Session]] = {}
    broker: BaseMessageBroker | None = None

    @classmethod
    def set_broker(cls, broker: BaseMessageBroker) -> None:
        cls.broker = broker

    @classmethod
    def get_or_create(cls, client: Client, session_id: int) -> tuple[Session, bool]:
        if session_id not in cls.sessions:
            cls.sessions[session_id] = {}
        if client.auth_data.auth_key_id in cls.sessions[session_id]:
            return cls.sessions[session_id][client.auth_data.auth_key_id], False

        session = Session(
            client=client,
            session_id=session_id,
            auth_key=KeyInfo(
                auth_key=client.auth_data.auth_key,
                auth_key_id=client.auth_data.auth_key_id,
            ),
        )
        cls.sessions[session_id][client.auth_data.auth_key_id] = session
        return session, True

    @classmethod
    def cleanup(cls, session: Session) -> None:
        key_id = session.auth_key.auth_key_id
        if session.session_id in cls.sessions and key_id in cls.sessions[session.session_id]:
            del cls.sessions[session.session_id][key_id]

    @classmethod
    async def send(
            cls, obj: TLObject, user_id: int | None = None, key_id: int | None = None, channel_id: int | None = None,
    ) -> None:
        if not user_id and not key_id and not channel_id:
            return

        await cls.broker.send(MessageToUsersShort(
            user=user_id,
            key_id=key_id,
            channel_id=channel_id,
            obj=obj,
        ))

    @classmethod
    async def subscribe_to_channel(cls, channel_id: int, user_ids: list[int]) -> None:
        if user_ids and channel_id:
            await cls.broker.send(ChannelSubscribe(channel_ids=[channel_id], user_ids=user_ids, subscribe=True))

    @classmethod
    async def unsubscribe_from_channel(cls, channel_id: int, user_ids: list[int]) -> None:
        if user_ids and channel_id:
            await cls.broker.send(ChannelSubscribe(channel_ids=[channel_id], user_ids=user_ids, subscribe=False))
