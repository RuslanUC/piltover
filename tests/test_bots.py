from contextlib import AsyncExitStack

import pytest
from pyrogram import filters
from pyrogram.raw.types import UpdateNewMessage, UpdateEditMessage
from pyrogram.raw.types.messages import BotCallbackAnswer
from pyrogram.types import Message as PyroMessage, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery

from piltover.db.models import User, Username, Bot, State
from tests.client import TestClient


@pytest.mark.real_auth
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


async def _create_bots(owner: User, count: int, username_prefix: str = "") -> list[Bot]:
    await User.bulk_create([
        User(phone_number=None, first_name=f"Bot #{i}", bot=True)
        for i in range(count)
    ])

    usernames_to_create = []
    bots_to_create = []
    states_to_create = []

    for bot_user in await User.filter(bot=True, first_name__startswith="Bot #"):
        num = int(bot_user.first_name.replace("Bot #", ""))
        usernames_to_create.append(Username(user=bot_user, username=f"{username_prefix}test_{num}_bot"))
        bots_to_create.append(Bot(owner=owner, bot=bot_user))
        states_to_create.append(State(user=bot_user))

    await Username.bulk_create(usernames_to_create)
    await Bot.bulk_create(bots_to_create)
    await State.bulk_create(states_to_create)

    return await Bot.filter(owner=owner)


@pytest.mark.real_auth
@pytest.mark.parametrize(
    ("bots_count", "check_text", "rows_count", "has_page_buttons"),
    [
        (0, "no bots", 0, False),
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
        await _create_bots(db_user, bots_count)

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


@pytest.mark.real_auth
@pytest.mark.asyncio
async def test_botfather_mybots_pagination(exit_stack: AsyncExitStack) -> None:
    client: TestClient = await exit_stack.enter_async_context(TestClient(phone_number="123456789"))

    db_user = await User.get_or_none(phone_number="123456789")
    await _create_bots(db_user, 7)

    await client.send_message("botfather", "/mybots")

    _, bot_response = await client.expect_updates(UpdateNewMessage, UpdateNewMessage)
    bot_message = await PyroMessage._parse(
        client,
        bot_response.message,
        {},
        {},
    )
    assert "Choose a bot" in bot_message.text
    assert isinstance(bot_message.reply_markup, InlineKeyboardMarkup)
    assert len(bot_message.reply_markup.inline_keyboard) == 4
    btn_text = bot_message.reply_markup.inline_keyboard[-1][-1].text
    assert btn_text == "->"

    await bot_message.click("->")

    new_response = await client.expect_updates(UpdateEditMessage)
    assert new_response
    new_response = new_response[0]
    new_message = await PyroMessage._parse(
        client,
        new_response.message,
        {},
        {},
    )
    assert "Choose a bot" in new_message.text
    assert isinstance(new_message.reply_markup, InlineKeyboardMarkup)
    assert len(new_message.reply_markup.inline_keyboard) == 2
    assert new_message.reply_markup.inline_keyboard[-1][-1].text == "<-"

    await new_message.click("<-")

    new_response = await client.expect_updates(UpdateEditMessage)
    assert new_response
    new_response = new_response[0]
    new_message = await PyroMessage._parse(client, new_response.message, {}, {})
    assert "Choose a bot" in new_message.text
    assert isinstance(new_message.reply_markup, InlineKeyboardMarkup)
    assert len(new_message.reply_markup.inline_keyboard) == 4
    assert new_message.reply_markup.inline_keyboard[-1][-1].text == "->"

    assert new_message.reply_markup == bot_message.reply_markup


@pytest.mark.real_auth
@pytest.mark.asyncio
async def test_bot_send_message_get_response(exit_stack: AsyncExitStack) -> None:
    client: TestClient = await exit_stack.enter_async_context(TestClient(phone_number="123456789"))

    db_user = await User.get_or_none(phone_number="123456789")
    bot, = await _create_bots(db_user, 1)

    token = f"{bot.bot_id}:{bot.token_nonce}"
    bot_client: TestClient = await exit_stack.enter_async_context(TestClient(bot_token=token))

    @bot_client.on_message(filters.command("start"))
    async def start_handler(_: TestClient, message: PyroMessage) -> None:
        await message.reply("123", quote=True)

    start_message = await client.send_message("test_0_bot", "/start")
    await client.expect_update(UpdateNewMessage)

    bot_response = await client.expect_update(UpdateNewMessage)
    assert bot_response.message.message == "123"
    assert bot_response.message.reply_to.reply_to_msg_id == start_message.id


@pytest.mark.real_auth
@pytest.mark.asyncio
async def test_bot_send_callback_query_get_response(exit_stack: AsyncExitStack) -> None:
    client: TestClient = await exit_stack.enter_async_context(TestClient(phone_number="123456789"))

    db_user = await User.get_or_none(phone_number="123456789")
    bot, = await _create_bots(db_user, 1)

    token = f"{bot.bot_id}:{bot.token_nonce}"
    bot_client: TestClient = await exit_stack.enter_async_context(TestClient(bot_token=token))

    @bot_client.on_message(filters.command("start"))
    async def start_handler(_: TestClient, message: PyroMessage) -> None:
        await message.reply("123", reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="test", callback_data="test_callback_data")
            ]
        ]))

    @bot_client.on_callback_query()
    async def callback_query_handler(_: TestClient, callback_query: CallbackQuery) -> None:
        await callback_query.answer("test response 123", show_alert=True)

    await client.send_message("test_0_bot", "/start")
    await client.expect_update(UpdateNewMessage)

    bot_response = await client.expect_update(UpdateNewMessage)
    assert bot_response.message.message == "123"
    bot_message = await PyroMessage._parse(client, bot_response.message, {}, {})
    assert len(bot_message.reply_markup.inline_keyboard) == 1
    assert bot_message.reply_markup.inline_keyboard[0][0].text == "test"

    resp: BotCallbackAnswer = await bot_message.click(0, 0)
    assert resp.message == "test response 123"
    assert resp.alert
