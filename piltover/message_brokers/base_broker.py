from __future__ import annotations

from abc import abstractmethod, ABC
from copy import deepcopy
from enum import Flag
from typing import TYPE_CHECKING, Iterable

from loguru import logger

from piltover.cache import Cache
from piltover.tl.types.internal import MessageToUsers, MessageToUsersShort, SetSessionInternalPush, ChannelSubscribe

if TYPE_CHECKING:
    from piltover.session_manager import Session


class BrokerType(Flag):
    READ = 1 << 0
    WRITE = 1 << 1


InternalMessages = MessageToUsers | MessageToUsersShort | SetSessionInternalPush


class BaseMessageBroker(ABC):
    def __init__(self, broker_type: BrokerType) -> None:
        self.broker_type = broker_type

        self.subscribed_users: dict[int, set[Session]] = {}
        self.subscribed_sessions: dict[int, Session] = {}
        self.subscribed_keys: dict[int, set[Session]] = {}
        self.subscribed_auths: dict[int, set[Session]] = {}
        self.subscribed_channels: dict[int, set[Session]] = {}

    @abstractmethod
    async def startup(self) -> None: ...

    @abstractmethod
    async def shutdown(self) -> None: ...

    @abstractmethod
    async def send(self, message: InternalMessages) -> None: ...

    @abstractmethod
    async def _listen(self) -> None: ...

    def subscribe_user(self, user_id: int, session: Session) -> None:
        if user_id:
            if user_id not in self.subscribed_users:
                self.subscribed_users[user_id] = set()

            self.subscribed_users[user_id].add(session)

    def subscribe_key(self, key_id: int, session: Session) -> None:
        if key_id:
            if key_id not in self.subscribed_keys:
                self.subscribed_keys[key_id] = set()

            self.subscribed_keys[key_id].add(session)

    def subscribe_auth(self, auth_id: int, session: Session) -> None:
        if auth_id:
            if auth_id not in self.subscribed_auths:
                self.subscribed_auths[auth_id] = set()

            self.subscribed_auths[auth_id].add(session)

    def subscribe(self, session: Session) -> None:
        self.subscribed_sessions[session.session_id] = session

        self.subscribe_user(session.user_id, session)
        self.subscribe_key(session.auth_key.auth_key_id if session.auth_key else None, session)
        self.subscribe_auth(session.auth_id, session)

        self.channels_diff_update(session, [], session.channel_ids)

    def unsubscribe_user(self, user_id: int, session: Session) -> None:
        if user_id in self.subscribed_users:
            if session in self.subscribed_users[user_id]:
                self.subscribed_users[user_id].remove(session)
            if not self.subscribed_users[user_id]:
                del self.subscribed_users[user_id]

    def unsubscribe_key(self, key_id: int, session: Session) -> None:
        if key_id in self.subscribed_keys:
            if session in self.subscribed_keys[key_id]:
                self.subscribed_keys[key_id].remove(session)
            if not self.subscribed_keys[key_id]:
                del self.subscribed_keys[key_id]

    def unsubscribe_auth(self, auth_id: int, session: Session) -> None:
        if auth_id in self.subscribed_auths:
            if session in self.subscribed_auths[auth_id]:
                self.subscribed_auths[auth_id].remove(session)
            if not self.subscribed_auths[auth_id]:
                del self.subscribed_auths[auth_id]

    def unsubscribe(self, session: Session) -> None:
        self.subscribed_sessions.pop(session.session_id, None)

        self.unsubscribe_user(session.user_id, session)
        self.unsubscribe_key(session.auth_key.auth_key_id if session.auth_key else None, session)
        self.unsubscribe_auth(session.auth_id, session)

        self.channels_diff_update(session, session.channel_ids, [])

    def channels_diff_update(self, session: Session, to_delete: Iterable[int], to_add: Iterable[int]) -> None:
        if not to_delete and not to_add:
            return

        for channel_id in to_delete:
            if channel_id not in self.subscribed_channels:
                continue
            if session in self.subscribed_channels[channel_id]:
                self.subscribed_channels[channel_id].remove(session)
            if not self.subscribed_channels[channel_id]:
                del self.subscribed_channels[channel_id]

        for channel_id in to_add:
            if channel_id not in self.subscribed_channels:
                self.subscribed_channels[channel_id] = set()

            self.subscribed_channels[channel_id].add(session)

    async def _process_message_to_users(self, message: MessageToUsers | MessageToUsersShort) -> None:
        if isinstance(message, MessageToUsers):
            users = message.users
            channels = message.channel_ids
            keys = message.key_ids
            auths = message.auth_ids
        else:
            users = [message.user] if message.user is not None else None
            channels = [message.channel_id] if message.channel_id is not None else None
            keys = [message.key_id] if message.key_id is not None else None
            auths = [message.auth_id] if message.auth_id is not None else None

        send_to = set()

        if users:
            for user_id in users:
                if user_id not in self.subscribed_users:
                    continue
                send_to.update(self.subscribed_users[user_id])

        if keys:
            for key_id in keys:
                if key_id not in self.subscribed_keys:
                    continue
                send_to.update(self.subscribed_keys[key_id])

        if channels:
            for channel_id in channels:
                if channel_id not in self.subscribed_channels:
                    continue
                send_to.update(self.subscribed_channels[channel_id])

        if auths:
            for auth_id in auths:
                if auth_id not in self.subscribed_auths:
                    continue
                send_to.update(self.subscribed_auths[auth_id])

        for session in send_to:
            try:
                await session.send(deepcopy(message.obj))
            except Exception as e:
                logger.opt(exception=e).error("Error occurred while sending message")

    async def _process_channels_subscribe(self, message: ChannelSubscribe) -> None:
        sessions = set()
        for user_id in message.user_ids:
            if user_id not in self.subscribed_users:
                continue
            sessions.update(self.subscribed_users[user_id])

        to_add, to_delete = message.channel_ids, []
        if not message.subscribe:
            to_add, to_delete = to_delete, to_add

        for user_id in message.user_ids:
            await Cache.obj.delete(f"channels:{user_id}")

        for session in sessions:
            self.channels_diff_update(session, to_delete, to_add)

    async def process_message(self, message: InternalMessages) -> None:
        if isinstance(message, (MessageToUsers, MessageToUsersShort)):
            return await self._process_message_to_users(message)
        if isinstance(message, SetSessionInternalPush):
            from piltover.session_manager import SessionManager
            if message.session_id not in SessionManager.sessions:
                return
            if message.key_id not in SessionManager.sessions[message.session_id]:
                return
            SessionManager.sessions[message.session_id][message.key_id].set_user_id(message.user_id)
            return
        if isinstance(message, ChannelSubscribe):
            return await self._process_channels_subscribe(message)
