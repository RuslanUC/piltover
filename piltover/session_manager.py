from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from time import time
from typing import TYPE_CHECKING

from mtproto.packets import DecryptedMessagePacket

from piltover.db.models import User, UserAuthorization, AuthKey
from piltover.layer_converter.manager import LayerConverter
from piltover.tl import TLObject, Updates
from piltover.tl.core_types import Message, MsgContainer
from piltover.tl.utils import is_content_related
from piltover.utils.utils import SingletonMeta

if TYPE_CHECKING:
    from piltover.server import Client


@dataclass(slots=True)
class KeyInfo:
    auth_key: bytes
    auth_key_id: int


@dataclass
class Session:
    client: Client | None
    session_id: int
    auth_key: KeyInfo | None = None
    user_id: int | None = None
    user: User | None = None
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

    def cleanup(self) -> None:
        self.online = False
        SessionManager.cleanup(self)


class SessionManager(metaclass=SingletonMeta):
    sessions: dict[int, dict[int, Session]] = {}
    by_key_id: dict[int, set[Session]] = defaultdict(set)
    by_user_id: dict[int, set[Session]] = defaultdict(set)

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
        cls.by_key_id[session.auth_key.auth_key_id].add(session)
        return session, True

    @classmethod
    def cleanup(cls, session: Session) -> None:
        key_id = session.auth_key.auth_key_id
        if session.session_id in cls.sessions and key_id in cls.sessions[session.session_id]:
            del cls.sessions[session.session_id][key_id]

        if key_id in cls.by_key_id:
            cls.by_key_id[key_id].remove(session)

        if session.user_id in cls.by_key_id:
            cls.by_user_id[session.user_id].remove(session)

    @classmethod
    def set_user_id(cls, session: Session, user_id: int) -> None:
        cls.by_user_id[user_id].add(session)
        session.user_id = user_id
        session.online = True

    @classmethod
    def set_user(cls, session: Session, user: User) -> None:
        cls.set_user_id(session, user.id)
        session.user = user.id

    @classmethod
    async def send(
            cls, obj: TLObject, user_id: int | None = None, key_id: int | None = None, *,
            exclude: list[Session] | None = None
    ) -> None:
        if user_id is None and key_id is None:
            return

        sessions = set()

        if user_id is not None:
            sessions.update(cls.by_user_id[user_id])
        if key_id is not None:
            sessions.update(cls.by_key_id[key_id])

        for session in sessions:
            if exclude is not None and session in exclude or not session.online:
                continue
            if isinstance(obj, Updates):
                key = await AuthKey.get_or_temp(session.auth_key.auth_key_id)
                auth = await UserAuthorization.get(key__id=str(key.id if isinstance(key, AuthKey) else key.perm_key.id))
                await auth.update(upd_seq=auth.upd_seq + 1)
                obj.seq = auth.upd_seq

            await session.client.send(obj, session)
