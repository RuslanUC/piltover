import pytest

from tests.conftest import TestClient


@pytest.mark.asyncio
async def test_change_profile() -> None:
    async with TestClient(phone_number="123456789") as client:
        assert client.me

        assert await client.update_profile(first_name="test 123")
        assert await client.update_profile(last_name="test asd")
        assert await client.update_profile(bio="test bio")

        me = await client.get_me()

        assert me.first_name == "test 123"
        assert me.last_name == "test asd"


@pytest.mark.asyncio
async def test_change_username() -> None:
    async with TestClient(phone_number="123456789") as client:
        assert client.me

        assert await client.set_username("test_username")

        me = await client.get_me()

        assert me.username == "test_username"
