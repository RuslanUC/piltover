from contextlib import AsyncExitStack

import pytest
from pyrogram.raw.types import UpdateNewMessage
from pyrogram.types import Message as PyroMessage, InlineKeyboardMarkup

from piltover.db.models import User, Username, Bot
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


@pytest.mark.parametrize(
    ("bots_count", "check_text", "rows_count", "has_page_buttons"),
    [
        (0, "No bots", 0, False),
        (1, "Choose a bot", 1, False),
        (2, "Choose a bot", 1, False),
        (3, "Choose a bot", 2, False),
        (6, "Choose a bot", 3, False),
        (7, "Choose a bot", 4, True),
    ],
    ids=("no-bots", "one-bot", "two-bots", "three-bots", "six-bots", "seven-bots"),
)
@pytest.mark.asyncio
async def test_botfather_mybots(
        exit_stack: AsyncExitStack, bots_count: int, check_text: str, rows_count: int, has_page_buttons: bool
) -> None:
    client: TestClient = await exit_stack.enter_async_context(TestClient(phone_number="123456789"))

    db_user = await User.get_or_none(phone_number="123456789")

    if bots_count:
        await User.bulk_create([
            User(phone_number=None, first_name=f"Bot #{i}", bot=True)
            for i in range(bots_count)
        ])

        usernames_to_create = []
        bots_to_create = []

        for bot_user in await User.filter(bot=True, first_name__startswith="Bot #"):
            num = int(bot_user.first_name.replace("Bot #", ""))
            usernames_to_create.append(Username(user=bot_user, username=f"test_{num}_bot"))
            bots_to_create.append(Bot(owner=db_user, bot=bot_user))

        await Username.bulk_create(usernames_to_create)
        await Bot.bulk_create(bots_to_create)

    await client.send_message("botfather", "/mybots")

    _, bot_response = await client.expect_updates(UpdateNewMessage, UpdateNewMessage)
    bot_message = await PyroMessage._parse(
        client,
        bot_response.message,
        {},
        {},
    )
    assert check_text in bot_message.text

    if rows_count:
        assert isinstance(bot_message.reply_markup, InlineKeyboardMarkup)
        assert len(bot_message.reply_markup.inline_keyboard) == rows_count

    if has_page_buttons:
        btn_text = bot_message.reply_markup.inline_keyboard[-1][-1].text
        assert btn_text in ("->", "<-")
