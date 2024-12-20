import pytest

from tests.conftest import TestClient


@pytest.mark.asyncio
async def test_signup() -> None:
    async with TestClient(phone_number="123456789") as client:
        assert await client.storage.user_id() is not None


@pytest.mark.asyncio
async def test_signin() -> None:
    async with TestClient(phone_number="123456789") as client:
        assert client.me
        user_id = client.me.id

    async with TestClient(phone_number="123456789") as client:
        assert client.me
        assert client.me.id == user_id
