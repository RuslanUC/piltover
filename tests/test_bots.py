from contextlib import AsyncExitStack

import pytest
from pyrogram.raw.types import UpdateNewMessage

from tests.client import TestClient


@pytest.mark.asyncio
async def test_create_botfather_bot(exit_stack: AsyncExitStack) -> None:
    client: TestClient = await exit_stack.enter_async_context(TestClient(phone_number="123456789"))

    await client.send_message("botfather", "/start")

    _, bot_response = await client.expect_updates(UpdateNewMessage, UpdateNewMessage)
    assert "/newbot - create a new bot" in bot_response.message.message

    await client.send_message("botfather", "/newbot")

    _, bot_response = await client.expect_updates(UpdateNewMessage, UpdateNewMessage)
    assert "Alright, a new bot" in bot_response.message.message

    await client.send_message("botfather", "test user-created bot")

    _, bot_response = await client.expect_updates(UpdateNewMessage, UpdateNewMessage)
    assert "Good." in bot_response.message.message

    await client.send_message("botfather", "test_user_created_bot")

    _, bot_response = await client.expect_updates(UpdateNewMessage, UpdateNewMessage)
    assert "Congratulations on your new bot. You will find it at t.me/test_user_created_bot." in bot_response.message.message

    bot_user = await client.get_users("test_user_created_bot")
    assert bot_user
    assert bot_user.is_bot

    token = bot_response.message.message.split("HTTP API:")[1].split("Keep ")[0].strip()

    bot_client: TestClient = await exit_stack.enter_async_context(TestClient(bot_token=token))
    bot_me = await bot_client.get_me()
    assert bot_me
    assert bot_me.is_bot
    assert bot_me.username == "test_user_created_bot"
