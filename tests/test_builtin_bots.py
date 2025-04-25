import pytest
from pyrogram.raw.types import UpdateNewMessage

from tests.conftest import TestClient


@pytest.mark.asyncio
async def test_test_bot_ping_command() -> None:
    async with TestClient(phone_number="123456789") as client:
        test_bot = await client.get_users("test_bot")

        await client.send_message(test_bot.id, "/ping")

        user_message = await client.expect_update(UpdateNewMessage)
        bot_message = await client.expect_update(UpdateNewMessage)

        if user_message.message.from_id.user_id != client.me.id:
            user_message, bot_message = bot_message, user_message

        assert user_message.message.from_id.user_id == client.me.id
        assert user_message.message.message == "/ping"

        assert bot_message.message.from_id.user_id == test_bot.id
        assert bot_message.message.message == "Pong"
