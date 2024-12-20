from types import SimpleNamespace

import pytest
from pyrogram.session import Auth

from piltover.server import Server


@pytest.mark.asyncio
async def test_key_generation(app_server: Server) -> None:
    client_ = SimpleNamespace()
    setattr(client_, "ipv6", False)
    setattr(client_, "proxy", None)
    auth_key = await Auth(client_, 2, False).create()
    assert auth_key is not None
