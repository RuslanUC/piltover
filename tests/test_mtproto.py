from types import SimpleNamespace
from typing import Any

import pytest
from pyrogram.errors import BadRequest
from pyrogram.raw.core import TLObject
from pyrogram.session import Auth

from tests.conftest import ClientFactory


@pytest.mark.real_key_gen
@pytest.mark.asyncio
async def test_key_generation() -> None:
    client_ = SimpleNamespace()
    setattr(client_, "ipv6", False)
    setattr(client_, "proxy", None)
    auth_key = await Auth(client_, 2, False).create()
    assert auth_key is not None


@pytest.mark.asyncio
async def test_invalid_method(client_with_auth: ClientFactory) -> None:
    class InvalidObject(TLObject):
        def write(self, *args: Any) -> bytes:
            return b"test"

    client = await client_with_auth(run=True)

    with pytest.raises(BadRequest, match="INPUT_METHOD_INVALID_1953719668_"):
        await client.invoke(InvalidObject())
