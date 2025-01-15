from __future__ import annotations

from abc import abstractmethod, ABC
from enum import Flag
from typing import TYPE_CHECKING

from piltover.tl.types.internal import Message

if TYPE_CHECKING:
    from piltover.session_manager import Session


class BrokerType(Flag):
    READ = 1 << 0
    WRITE = 1 << 1


class BaseMessageBroker(ABC):
    def __init__(self, broker_type: BrokerType) -> None:
        self.broker_type = broker_type

        self.subscribed_users: dict[int, set[Session]] = {}
        self.subscribed_sessions: dict[int, Session] = {}
        self.subscribed_keys: dict[int, set[Session]] = {}

    @abstractmethod
    async def startup(self) -> None: ...

    @abstractmethod
    async def shutdown(self) -> None: ...

    @abstractmethod
    async def send(self, message: Message) -> None: ...

    @abstractmethod
    async def _listen(self) -> None: ...

    def subscribe(self, session: Session) -> None:
        self.subscribed_sessions[session.session_id] = session

        if session.auth_key:
            key_id = session.auth_key.auth_key_id
            if key_id not in self.subscribed_keys:
                self.subscribed_keys[key_id] = set()

            self.subscribed_keys[key_id].add(session)

        if session.user_id:
            if session.user_id not in self.subscribed_users:
                self.subscribed_users[session.user_id] = set()

            self.subscribed_users[session.user_id].add(session)

    def unsubscribe(self, session: Session) -> None:
        self.subscribed_sessions.pop(session.session_id, None)

        if session.user_id in self.subscribed_users:
            if session in self.subscribed_users[session.user_id]:
                self.subscribed_users[session.user_id].remove(session)
            if not self.subscribed_users[session.user_id]:
                del self.subscribed_users[session.user_id]

        key_id = session.auth_key.auth_key_id if session.auth_key else None
        if key_id in self.subscribed_keys:
            if session in self.subscribed_keys[key_id]:
                self.subscribed_keys[key_id].remove(session)
            if not self.subscribed_keys[key_id]:
                del self.subscribed_keys[key_id]

    async def process_message(self, message: Message) -> None:
        # TODO: process system (?) message

        send_to = set()

        if message.users:
            for user_id in message.users:
                if user_id not in self.subscribed_users:
                    continue
                for session in self.subscribed_users[user_id]:
                    send_to.add(session)

        if message.sessions:
            for session_id in message.sessions:
                if session_id not in self.subscribed_sessions:
                    continue
                send_to.add(self.subscribed_sessions[session_id])

        if message.key_ids:
            for key_id in message.users:
                if key_id not in self.subscribed_keys:
                    continue
                for session in self.subscribed_keys[key_id]:
                    send_to.add(session)

        for session in send_to:
            await session.send(message.obj)
