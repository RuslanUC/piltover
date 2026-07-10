from time import time
from types import SimpleNamespace
from typing import Any

import pytest
from pyrogram.errors import BadRequest
from pyrogram.raw.core import TLObject, FutureSalts
from pyrogram.raw.functions import GetFutureSalts
from pyrogram.session import Auth

from tests.client import TestClient
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


@pytest.mark.real_key_gen
@pytest.mark.asyncio
async def test_get_future_salts() -> None:
    client = TestClient(phone_number="123456789")

    async with client:
        salts = await client.invoke(GetFutureSalts(num=3))
        assert isinstance(salts, FutureSalts)
        assert len(salts.salts) == 3

        server_time = salts.now
        client_time = time()
        assert client_time - 3 <= server_time <= client_time

        assert salts.salts[0].valid_until - salts.salts[0].valid_since == 30 * 60
        assert salts.salts[1].valid_until - salts.salts[1].valid_since == 30 * 60
        assert salts.salts[2].valid_until - salts.salts[2].valid_since == 30 * 60

        assert salts.salts[0].valid_since < salts.salts[1].valid_since
        assert salts.salts[1].valid_since < salts.salts[2].valid_since


@pytest.mark.real_key_gen
@pytest.mark.asyncio
async def test_get_future_salts_lower_limit() -> None:
    client = TestClient(phone_number="123456789")

    async with client:
        salts = await client.invoke(GetFutureSalts(num=0))
        assert isinstance(salts, FutureSalts)
        assert len(salts.salts) == 1

        salts = await client.invoke(GetFutureSalts(num=-50))
        assert len(salts.salts) == 1


@pytest.mark.real_key_gen
@pytest.mark.asyncio
async def test_get_future_salts_upper_limit() -> None:
    client = TestClient(phone_number="123456789")

    async with client:
        salts = await client.invoke(GetFutureSalts(num=65))
        assert isinstance(salts, FutureSalts)
        assert len(salts.salts) == 64
