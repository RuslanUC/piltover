from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from time import time
from typing import TYPE_CHECKING

from piltover.db.models import User, UserAuthorization, AuthKey
from piltover.tl import TLObject, Updates
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
    layer = 0

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
        # TODO(security) validate according to
        #  https://core.telegram.org/mtproto/service_messages_about_messages#notice-of-ignored-error-message

    def get_outgoing_seq_no(self, obj: TLObject) -> int:
        ret = self.outgoing_content_related_msgs * 2
        if is_content_related(obj):
            self.outgoing_content_related_msgs += 1
            ret += 1
        return ret

    def __hash__(self) -> int:
        return self.session_id


class SessionManager(metaclass=SingletonMeta):
    def __init__(self):
        self.sessions: dict[int, dict[int, Session]] = {}
        self.by_client: dict[Client, set[Session]] = defaultdict(set)
        self.by_key_id: dict[int, set[Session]] = defaultdict(set)
        self.by_user_id: dict[int, set[Session]] = defaultdict(set)

    def get_or_create(self, client: Client, session_id: int) -> tuple[Session, bool]:
        if session_id not in self.sessions:
            self.sessions[session_id] = {}
        if client.auth_data.auth_key_id in self.sessions[session_id]:
            return self.sessions[session_id][client.auth_data.auth_key_id], False

        session = Session(
            client=client,
            session_id=session_id,
            auth_key=KeyInfo(
                auth_key=client.auth_data.auth_key,
                auth_key_id=client.auth_data.auth_key_id,
            ),
        )
        self.sessions[session_id][client.auth_data.auth_key_id] = session
        self.by_client[client].add(session)
        self.by_key_id[session.auth_key.auth_key_id].add(session)
        return session, True

    def client_cleanup(self, client: Client) -> None:
        if (sessions := self.by_client.get(client, None)) is None:
            return

        del self.by_client[client]
        for session in sessions:
            del self.sessions[session.session_id][session.auth_key.auth_key_id]
            self.by_key_id[session.auth_key.auth_key_id].remove(session)
            if session.user_id is not None:
                self.by_user_id[session.user_id].remove(session)

    def set_user_id(self, session: Session, user_id: int) -> None:
        self.by_user_id[user_id].add(session)
        session.user_id = user_id

    def set_user(self, session: Session, user: User) -> None:
        self.set_user_id(session, user.id)
        session.user = user.id

    async def send(self, obj: TLObject, user_id: int | None = None, key_id: int | None = None, *,
                   exclude: list[Client] | None = None) -> None:
        if user_id is None and key_id is None:
            return

        sessions = set()

        if user_id is not None:
            sessions.update(self.by_user_id[user_id])
        if key_id is not None:
            sessions.update(self.by_key_id[key_id])

        #print(f"[{user_id}] sent {obj} ({obj.write()})")

        for session in sessions:
            if (exclude is not None and session.client in exclude) or session.client not in self.by_client:
                continue
            if isinstance(obj, Updates):
                key = await AuthKey.get_or_temp(session.auth_key.auth_key_id)
                auth = await UserAuthorization.get(key__id=str(key.id if isinstance(key, AuthKey) else key.perm_key.id))
                await auth.update(upd_seq=auth.upd_seq+1)
                obj.seq = auth.upd_seq

            await session.client.send(obj, session)
