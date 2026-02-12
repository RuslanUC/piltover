from contextlib import AsyncExitStack
from typing import cast

import pytest
from pyrogram.emoji import THUMBS_UP, THUMBS_DOWN
from pyrogram.raw.functions.messages import GetMessagesReactions
from pyrogram.raw.types import Updates, UpdateMessageReactions, ReactionCount
from pyrogram.raw.types.messages import AvailableReactionsNotModified

from piltover.app.app import args as app_args
from piltover.tl.functions.messages import GetAvailableReactions
from tests.client import TestClient


@pytest.mark.asyncio
async def test_get_available_reactions_empty() -> None:
    async with TestClient(phone_number="123456789") as client:
        reactions = await client.invoke_p(GetAvailableReactions(hash=1))
        assert len(reactions.reactions) == 0
        assert reactions.hash == 0

        reactions = await client.invoke_p(GetAvailableReactions(hash=0))
        assert isinstance(reactions, AvailableReactionsNotModified)


reactions_files_dir = app_args.reactions_dir / "files"
skip_reactions_test = pytest.mark.skipif(
    not reactions_files_dir.exists(), reason="No reactions files available"
)


@skip_reactions_test
@pytest.mark.create_reactions
@pytest.mark.asyncio
async def test_get_available_reactions() -> None:
    async with TestClient(phone_number="123456789") as client:
        reactions = await client.invoke_p(GetAvailableReactions(hash=0))
        assert len(reactions.reactions) > 0


@skip_reactions_test
@pytest.mark.create_reactions
@pytest.mark.asyncio
async def test_send_reaction_in_private_chat(exit_stack: AsyncExitStack) -> None:
    client1: TestClient = await exit_stack.enter_async_context(TestClient(phone_number="123456789"))
    client2: TestClient = await exit_stack.enter_async_context(TestClient(phone_number="123456780"))
    await client1.resolve_user(client2, False)
    await client2.resolve_user(client1, False)

    async def _check(
            client: TestClient, other_id: int, message_id: int, updates_count: int, up_count: int, down_count: int
    ):
        updates = cast(Updates, await client.invoke(GetMessagesReactions(
            peer=await client.resolve_peer(other_id),
            id=[message_id],
        )))
        assert len(updates.updates) == updates_count
        if not updates_count:
            return

        assert isinstance(updates.updates[0], UpdateMessageReactions)
        update = cast(UpdateMessageReactions, updates.updates[0])
        assert update.msg_id == message_id
        results_count = (up_count > 0) + (down_count > 0)
        assert len(update.reactions.results) == results_count
        if not results_count:
            return

        results = cast(list[ReactionCount], update.reactions.results)
        reaction_to_count = {
            result.reaction.emoticon: result.count
            for result in results
        }
        if up_count:
            assert THUMBS_UP in reaction_to_count
            assert reaction_to_count[THUMBS_UP] == up_count
        else:
            assert THUMBS_UP not in reaction_to_count

        if down_count:
            assert THUMBS_DOWN in reaction_to_count
            assert reaction_to_count[THUMBS_DOWN] == down_count
        else:
            assert THUMBS_DOWN not in reaction_to_count

    message1 = await client1.send_message(client2.me.id, "test message")
    message2 = [m async for m in client2.get_chat_history(client1.me.id)][0]

    await _check(client1, client2.me.id, message1.id, 1, 0, 0)
    await _check(client2, client1.me.id, message2.id, 1, 0, 0)

    assert await client1.send_reaction(client2.me.id, message1.id, THUMBS_UP)
    await _check(client1, client2.me.id, message1.id, 1, 1, 0)
    await _check(client2, client1.me.id, message2.id, 1, 1, 0)

    assert await client2.send_reaction(client1.me.id, message2.id, THUMBS_DOWN)
    await _check(client1, client2.me.id, message1.id, 1, 1, 1)
    await _check(client2, client1.me.id, message2.id, 1, 1, 1)
