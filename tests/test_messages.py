import logging
from io import BytesIO

import pytest

from piltover.server import Server
from tests.conftest import TestClient


@pytest.mark.asyncio
async def test_send_text_message() -> None:
    async with TestClient(phone_number="123456789") as client:
        messages = [msg async for msg in client.get_chat_history("me")]
        assert len(messages) == 0

        message = await client.send_message("me", text="test 123")
        assert message.text == "test 123"

        messages = [msg async for msg in client.get_chat_history("me")]
        assert len(messages) == 1

        assert messages[0].id == message.id
        assert messages[0].text == message.text


@pytest.mark.asyncio
async def test_send_message_with_document() -> None:
    async with TestClient(phone_number="123456789") as client:
        file = BytesIO(b"test document")
        setattr(file, "name", "test.txt")
        message = await client.send_document("me", document=file)
        assert message.document is not None
        downloaded = await message.download(in_memory=True)
        assert downloaded.getvalue() == b"test document"


@pytest.mark.asyncio
async def test_edit_text_message() -> None:
    async with TestClient(phone_number="123456789") as client:
        message = await client.send_message("me", text="test 123")
        assert message.text == "test 123"

        new_message = await message.edit("test edited")

        assert new_message.id == message.id
        assert new_message.text == "test edited"


@pytest.mark.asyncio
async def test_delete_text_message() -> None:
    async with TestClient(phone_number="123456789") as client:
        messages = [msg async for msg in client.get_chat_history("me")]
        assert len(messages) == 0

        message = await client.send_message("me", text="test 123")
        assert message.text == "test 123"

        messages = [msg async for msg in client.get_chat_history("me")]
        assert len(messages) == 1

        assert messages[0].id == message.id
        assert messages[0].text == message.text

        await message.delete()

        messages = [msg async for msg in client.get_chat_history("me")]
        assert len(messages) == 0


@pytest.mark.asyncio
async def test_pin_message() -> None:
    async with TestClient(phone_number="123456789") as client:
        message = await client.send_message("me", text="test 123")
        assert message.text == "test 123"
        await message.pin()
