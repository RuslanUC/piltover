import logging

import pytest

from piltover.server import Server
from tests.conftest import TestClient

logging.basicConfig(level=logging.DEBUG)

@pytest.mark.asyncio
async def test_signup(app_server: Server) -> None:
    async with TestClient(phone_number="123456789", phone_code="22222") as client:
        assert await client.storage.user_id() is not None


@pytest.mark.asyncio
async def test_signin(app_server: Server) -> None:
    async with TestClient(phone_number="123456789", phone_code="22222") as client:
        assert client.me
        user_id = client.me.id

    async with TestClient(phone_number="123456789", phone_code="22222") as client:
        assert client.me
        assert client.me.id == user_id
