import asyncio
from asyncio import get_event_loop, Future, Queue
from contextlib import AsyncExitStack

import pytest
from tg_secret import TelegramSecretClient, ChatRequestResult, SecretChat, ChatState, SecretMessage
from tg_secret.client_adapters.pyrogram_adapter import PyrogramClientAdapter

from tests.conftest import TestClient


class WaitForSecretEvent:
    def __init__(self, client: TelegramSecretClient) -> None:
        self._messages_queue: Queue[SecretMessage] = Queue()
        self._ready_queue: Queue[SecretChat] = Queue()
        self._chat_deleted_queue: Queue[tuple[SecretChat, bool]] = Queue()

        client.add_new_message_handler(self._messages_queue.put)
        client.add_chat_ready_handler(self._ready_queue.put)
        client.add_chat_deleted_handler(self._chat_deleted_handler)

    async def _chat_deleted_handler(self, chat: SecretChat, history: bool) -> None:
        await self._chat_deleted_queue.put((chat, history))

    async def wait_for_message(self, timeout: int) -> SecretMessage:
        return await asyncio.wait_for(self._messages_queue.get(), timeout)

    async def wait_for_ready(self, timeout: int) -> SecretChat:
        return await asyncio.wait_for(self._ready_queue.get(), timeout)

    async def wait_for_chat_del(self, timeout: int) -> SecretChat:
        return await asyncio.wait_for(self._ready_queue.get(), timeout)


@pytest.mark.asyncio
async def test_request_accept_secret_chat(exit_stack: AsyncExitStack) -> None:
    loop = get_event_loop()

    client1 = TestClient(phone_number="123456789")
    client2 = TestClient(phone_number="1234567890")
    secret1 = TelegramSecretClient(PyrogramClientAdapter(client1), session_name="client1", in_memory=True)
    secret2 = TelegramSecretClient(PyrogramClientAdapter(client2), session_name="client2", in_memory=True)

    # secret clients need to be stopped first so they won't raise database errors after
    #  receiving secret chat updates from pyrogram clients
    await exit_stack.enter_async_context(secret1)
    await exit_stack.enter_async_context(secret2)
    await exit_stack.enter_async_context(client1)
    await exit_stack.enter_async_context(client2)

    wait1 = WaitForSecretEvent(secret1)
    wait2 = WaitForSecretEvent(secret2)

    await client2.set_username("client2_username")

    user1 = await client1.get_me()
    user2 = await client2.get_me()

    request_future: Future[SecretChat] = loop.create_future()

    @secret2.on_request
    async def secret_chat_request(chat: SecretChat) -> ChatRequestResult:
        request_future.set_result(chat)
        return ChatRequestResult.ACCEPT


    await secret1.request_encryption("client2_username")

    requested_chat = await asyncio.wait_for(request_future, 1)
    assert not requested_chat.originator
    assert requested_chat.state == ChatState.REQUESTED
    assert requested_chat.peer_id == user1.id

    ready1_chat = await wait1.wait_for_ready(1)
    assert ready1_chat.originator
    assert ready1_chat.state == ChatState.READY
    assert ready1_chat.peer_id == user2.id

    ready2_chat = await wait2.wait_for_ready(1)
    assert not ready2_chat.originator
    assert ready2_chat.state == ChatState.READY
    assert ready2_chat.peer_id == user1.id


@pytest.mark.asyncio
async def test_send_secret_message(exit_stack: AsyncExitStack) -> None:
    client1 = TestClient(phone_number="123456789")
    client2 = TestClient(phone_number="1234567890")
    secret1 = TelegramSecretClient(PyrogramClientAdapter(client1), session_name="client1", in_memory=True)
    secret2 = TelegramSecretClient(PyrogramClientAdapter(client2), session_name="client2", in_memory=True)

    # secret clients need to be stopped first so they won't raise database errors after
    #  receiving secret chat updates from pyrogram clients
    await exit_stack.enter_async_context(secret1)
    await exit_stack.enter_async_context(secret2)
    await exit_stack.enter_async_context(client1)
    await exit_stack.enter_async_context(client2)

    wait1 = WaitForSecretEvent(secret1)
    wait2 = WaitForSecretEvent(secret2)

    await client2.set_username("client2_username")

    user1 = await client1.get_me()
    user2 = await client2.get_me()

    @secret2.on_request
    async def secret_chat_request(_: SecretChat) -> ChatRequestResult:
        return ChatRequestResult.ACCEPT


    chat = await secret1.request_encryption("client2_username")
    assert chat is not None

    assert await wait1.wait_for_ready(1)
    assert await wait2.wait_for_ready(1)

    assert await secret1.send_text_message(chat.id, "test 1")
    assert await secret2.send_text_message(chat.id, "test 2")

    message2 = await wait1.wait_for_message(1)
    assert message2.from_id == user2.id
    assert message2.text == "test 2"

    message1 = await wait2.wait_for_message(1)
    assert message1.from_id == user1.id
    assert message1.text == "test 1"
