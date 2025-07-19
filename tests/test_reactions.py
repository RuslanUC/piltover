from typing import cast

import pytest
from pyrogram.raw.functions.messages import GetAvailableReactions
from pyrogram.raw.types.messages import AvailableReactions, AvailableReactionsNotModified

from tests.conftest import TestClient


@pytest.mark.asyncio
async def test_get_available_reactions_empty() -> None:
    async with TestClient(phone_number="123456789") as client:
        reactions = cast(AvailableReactions, await client.invoke(GetAvailableReactions(hash=1)))
        assert len(reactions.reactions) == 0
        assert reactions.hash == 0

        reactions = await client.invoke(GetAvailableReactions(hash=0))
        assert isinstance(reactions, AvailableReactionsNotModified)


@pytest.mark.create_reactions
@pytest.mark.asyncio
async def test_get_available_reactions() -> None:
    async with TestClient(phone_number="123456789") as client:
        reactions = cast(AvailableReactions, await client.invoke(GetAvailableReactions(hash=0)))
        assert len(reactions.reactions) > 0
