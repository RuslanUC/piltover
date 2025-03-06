import pytest
from pyrogram.errors import UsernameInvalid, UsernameOccupied, UsernameNotModified

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


@pytest.mark.asyncio
async def test_change_username_to_invalid() -> None:
    async with TestClient(phone_number="123456789") as client:
        for username in ("tes/t_username", "very_long_username"*100, "username.with.dots", ".", ":::"):
            with pytest.raises(UsernameInvalid):
                assert await client.set_username(username)

            me = await client.get_me()
            assert me.username is None


@pytest.mark.asyncio
async def test_change_username_to_occupied() -> None:
    async with TestClient(phone_number="123456789") as client, TestClient(phone_number="1234567890") as client2:
        assert await client.set_username("test_username")
        me = await client.get_me()
        assert me.username == "test_username"

        with pytest.raises(UsernameOccupied):
            assert await client2.set_username("test_username")

            me = await client2.get_me()
            assert me.username is None


@pytest.mark.asyncio
async def test_change_username_to_same() -> None:
    async with TestClient(phone_number="123456789") as client:
        with pytest.raises(UsernameNotModified):
            assert await client.set_username("")

        assert await client.set_username("test_username")
        me = await client.get_me()
        assert me.username == "test_username"

        with pytest.raises(UsernameNotModified):
            assert await client.set_username("test_username")

        me = await client.get_me()
        assert me.username == "test_username"


@pytest.mark.asyncio
async def test_resolve_username() -> None:
    async with TestClient(phone_number="123456789") as client, TestClient(phone_number="1234567890") as client2:
        await client2.set_username("test2_username")
        user2 = await client.get_users("test2_username")
        me2 = await client2.get_me()

        assert user2.id == me2.id
