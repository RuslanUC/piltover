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


@pytest.mark.asyncio
async def test_enable_disable_cloud_password() -> None:
    async with TestClient(phone_number="123456789") as client:
        assert client.me
        user_id = client.me.id

        assert await client.enable_cloud_password("test_passw0rd")

    async with TestClient(phone_number="123456789", password="test_passw0rd") as client:
        assert client.me
        assert client.me.id == user_id

        assert await client.change_cloud_password("test_passw0rd", "test_passw0rd_new")
        assert await client.remove_cloud_password("test_passw0rd_new")
