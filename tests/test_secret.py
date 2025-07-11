import asyncio
from asyncio import get_event_loop, Future
from contextlib import AsyncExitStack

import pytest
from tg_secret import TelegramSecretClient, ChatRequestResult, SecretChat, ChatState
from tg_secret.client_adapters.pyrogram_adapter import PyrogramClientAdapter

from tests.conftest import TestClient


@pytest.mark.asyncio
async def test_request_accept_secret_chat() -> None:
    loop = get_event_loop()

    async with AsyncExitStack() as stack:
        client1 = TestClient(phone_number="123456789")
        client2 = TestClient(phone_number="1234567890")
        secret1 = TelegramSecretClient(PyrogramClientAdapter(client1), session_name="client1", in_memory=True)
        secret2 = TelegramSecretClient(PyrogramClientAdapter(client2), session_name="client2", in_memory=True)

        # secret clients need to be stopped first so they won't raise database errors after
        #  receiving secret chat updates from pyrogram clients
        await stack.enter_async_context(secret1)
        await stack.enter_async_context(secret2)
        await stack.enter_async_context(client1)
        await stack.enter_async_context(client2)

        await client2.set_username("client2_username")

        user1 = await client1.get_me()
        user2 = await client2.get_me()

        request_future: Future[SecretChat] = loop.create_future()
        ready1_future: Future[SecretChat] = loop.create_future()
        ready2_future: Future[SecretChat] = loop.create_future()

        @secret2.on_request
        async def secret_chat_request(chat: SecretChat) -> ChatRequestResult:
            request_future.set_result(chat)
            return ChatRequestResult.ACCEPT

        @secret1.on_chat_ready
        async def secret_chat_ready(chat: SecretChat) -> None:
            ready1_future.set_result(chat)

        @secret2.on_chat_ready
        async def secret_chat_ready(chat: SecretChat) -> None:
            ready2_future.set_result(chat)


        await secret1.request_encryption("client2_username")

        requested_chat = await asyncio.wait_for(request_future, 1)
        assert not requested_chat.originator
        assert requested_chat.state == ChatState.REQUESTED
        assert requested_chat.peer_id == user1.id

        ready1_chat = await asyncio.wait_for(ready1_future, 1)
        assert ready1_chat.originator
        assert ready1_chat.state == ChatState.READY
        assert ready1_chat.peer_id == user2.id

        ready2_chat = await asyncio.wait_for(ready2_future, 1)
        assert not ready2_chat.originator
        assert ready2_chat.state == ChatState.READY
        assert ready2_chat.peer_id == user1.id
