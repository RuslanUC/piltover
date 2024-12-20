import logging

import pytest

from piltover.server import Server
from tests.conftest import TestClient

logging.basicConfig(level=logging.DEBUG)

@pytest.mark.asyncio
async def test_send_code(app_server: Server) -> None:
    async with TestClient(phone_number="123456789", phone_code="22222") as client:
        assert await client.storage.user_id() is not None
