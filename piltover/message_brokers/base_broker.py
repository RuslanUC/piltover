from __future__ import annotations

import asyncio
from abc import abstractmethod, ABC
from copy import deepcopy
from enum import Flag
from typing import TYPE_CHECKING, Iterable

from loguru import logger

from piltover.cache import Cache
from piltover.tl import UpdatesTooLong
from piltover.tl.base.internal import MessageInternal
from piltover.tl.types.internal import MessageToUsers, MessageToUsersShort, SetSessionInternalPush, ChannelSubscribe, \
    ObjectWithLayerRequirement, InternalPushForUsers, InternalPushForUsersShort

if TYPE_CHECKING:
    from piltover.session import Session


class BrokerType(Flag):
    READ = 1 << 0
    WRITE = 1 << 1


class BaseMessageBroker(ABC):
    def __init__(self, broker_type: BrokerType) -> None:
        self.broker_type = broker_type

        self.subscribed_users: dict[int, set[Session]] = {}
        self.subscribed_sessions: dict[int, Session] = {}
        self.subscribed_keys: dict[int, set[Session]] = {}
        self.subscribed_auths: dict[int, set[Session]] = {}
        self.subscribed_channels: dict[int, set[Session]] = {}
        self.internal_push_users: dict[int, set[Session]] = {}

    def _cleanup(self) -> None:
        self.subscribed_users.clear()
        self.subscribed_sessions.clear()
        self.subscribed_keys.clear()
        self.subscribed_auths.clear()
        self.subscribed_channels.clear()
        self.internal_push_users.clear()

    async def startup(self) -> None:
        self._cleanup()

    async def shutdown(self) -> None:
        self._cleanup()

    @abstractmethod
    async def send(self, message: MessageInternal) -> None: ...

    @abstractmethod
    async def _listen(self) -> None: ...

    def subscribe_user(self, user_id: int, session: Session) -> None:
        if not user_id:
            return

        if user_id not in self.subscribed_users:
            self.subscribed_users[user_id] = set()

        self.subscribed_users[user_id].add(session)

    def subscribe_key(self, key_id: int, session: Session) -> None:
        if not key_id:
            return

        if key_id not in self.subscribed_keys:
            self.subscribed_keys[key_id] = set()

        self.subscribed_keys[key_id].add(session)

    def subscribe_auth(self, auth_id: int, session: Session) -> None:
        if not auth_id:
            return

        if auth_id not in self.subscribed_auths:
            self.subscribed_auths[auth_id] = set()

        self.subscribed_auths[auth_id].add(session)

    def subscribe_internal_push(self, user_id: int, session: Session) -> None:
        if not user_id:
            return None

        if user_id not in self.internal_push_users:
            self.internal_push_users[user_id] = set()

        self.internal_push_users[user_id].add(session)

    def subscribe(self, session: Session) -> None:
        self.subscribed_sessions[session.session_id] = session

        self.subscribe_user(session.user_id, session)
        self.subscribe_key(session.auth_data.auth_key_id if session.auth_data else None, session)
        self.subscribe_key(session.auth_data.perm_auth_key_id if session.auth_data else None, session)
        self.subscribe_auth(session.auth_id, session)

        self.channels_diff_update(session, [], session.channel_ids)

        if session.is_internal_push:
            self.subscribe_internal_push(session.user_id, session)
        else:
            self.unsubscribe_internal_push(session.user_id, session)

    def unsubscribe_user(self, user_id: int, session: Session) -> None:
        if user_id not in self.subscribed_users:
            return

        if session in self.subscribed_users[user_id]:
            self.subscribed_users[user_id].remove(session)
        if not self.subscribed_users[user_id]:
            del self.subscribed_users[user_id]

    def unsubscribe_key(self, key_id: int, session: Session) -> None:
        if key_id not in self.subscribed_keys:
            return

        if session in self.subscribed_keys[key_id]:
            self.subscribed_keys[key_id].remove(session)
        if not self.subscribed_keys[key_id]:
            del self.subscribed_keys[key_id]

    def unsubscribe_auth(self, auth_id: int, session: Session) -> None:
        if auth_id not in self.subscribed_auths:
            return

        if session in self.subscribed_auths[auth_id]:
            self.subscribed_auths[auth_id].remove(session)
        if not self.subscribed_auths[auth_id]:
            del self.subscribed_auths[auth_id]

    def unsubscribe_internal_push(self, user_id: int, session: Session) -> None:
        if user_id not in self.internal_push_users:
            return

        if session in self.internal_push_users[user_id]:
            self.internal_push_users[user_id].remove(session)
        if not self.internal_push_users[user_id]:
            del self.internal_push_users[user_id]

    def unsubscribe(self, session: Session) -> None:
        self.subscribed_sessions.pop(session.session_id, None)

        self.unsubscribe_user(session.user_id, session)
        self.unsubscribe_key(session.auth_data.auth_key_id if session.auth_data else None, session)
        self.unsubscribe_key(session.auth_data.perm_auth_key_id if session.auth_data else None, session)
        self.unsubscribe_auth(session.auth_id, session)

        self.channels_diff_update(session, session.channel_ids, [])

        self.unsubscribe_internal_push(session.user_id, session)

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
            ignore_auths = set(message.ignore_auth_id) if message.ignore_auth_id is not None else set()
        else:
            users = [message.user] if message.user is not None else None
            channels = [message.channel_id] if message.channel_id is not None else None
            keys = [message.key_id] if message.key_id is not None else None
            auths = [message.auth_id] if message.auth_id is not None else None
            ignore_auths = {message.ignore_auth_id} if message.ignore_auth_id is not None else set()

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
                if auth_id in ignore_auths or auth_id not in self.subscribed_auths:
                    continue
                send_to.update(self.subscribed_auths[auth_id])

        logger.trace(
            "Got message {message!r} that will be sent to {count} sessions", message=message, count=len(send_to)
        )

        for session in send_to:
            if session.auth_id in ignore_auths or session.is_internal_push:
                continue
            try:
                if isinstance(message.obj, ObjectWithLayerRequirement):
                    await session.enqueue(deepcopy(message.obj), False)
                else:
                    await session.enqueue(message.obj, False)
            except Exception as e:
                logger.opt(exception=e).error("Error occurred while sending message")

    async def _process_channels_subscribe(self, message: ChannelSubscribe) -> None:
        logger.trace(f"Subscribing/unsubscribing {len(message.user_ids)} to {len(message.channel_ids)} channels...")

        sessions = set()
        for user_id in message.user_ids:
            if user_id not in self.subscribed_users:
                continue
            sessions.update(self.subscribed_users[user_id])

        logger.trace(f"Will subscribe/unsubscribe {len(sessions)} sessions...")
        logger.trace("{message!r}, {users}", message=message, users=self.subscribed_users)

        to_add, to_delete = message.channel_ids, []
        if not message.subscribe:
            to_add, to_delete = to_delete, to_add

        for user_id in message.user_ids:
            await Cache.obj.delete(f"channels:{user_id}")

        for session in sessions:
            self.channels_diff_update(session, to_delete, to_add)

    async def _process_internal_push_to_users(self, message: InternalPushForUsers | InternalPushForUsersShort) -> None:
        if isinstance(message, InternalPushForUsers):
            users = message.users
        else:
            users = [message.user]

        send_to = set()

        for user_id in users:
            await asyncio.sleep(0)
            if user_id not in self.internal_push_users:
                continue
            send_to.update(self.internal_push_users[user_id])

        logger.trace(f"Got internal push to {len(users)} users that will be sent to {len(send_to)} sessions")

        to_send = UpdatesTooLong()

        for session in send_to:
            try:
                await session.enqueue(to_send, False)
            except Exception as e:
                logger.opt(exception=e).error("Error occurred while sending internal push")

    async def _process_message(self, message: MessageInternal) -> None:
        if isinstance(message, (MessageToUsers, MessageToUsersShort)):
            return await self._process_message_to_users(message)
        if isinstance(message, SetSessionInternalPush):
            from piltover.session import SessionManager
            uniq_id = message.key_id, message.session_id
            if uniq_id not in SessionManager.sessions:
                return
            session = SessionManager.sessions[uniq_id]
            session.is_internal_push = True
            await session.refresh_auth_maybe(True)
            self.subscribe(session)
            logger.debug(f"Registered session {uniq_id} for internal push")
            return
        if isinstance(message, ChannelSubscribe):
            return await self._process_channels_subscribe(message)
        if isinstance(message, (InternalPushForUsers, InternalPushForUsersShort)):
            return await self._process_internal_push_to_users(message)

    async def process_message(self, message: MessageInternal) -> None:
        loop = asyncio.get_running_loop()
        loop.create_task(self._process_message(message))
