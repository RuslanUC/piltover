from contextlib import AsyncExitStack

import pytest
from pyrogram.errors import UsernameInvalid, UsernameOccupied, UsernameNotModified, TtlDaysInvalid
from pyrogram.raw.functions.account import CheckUsername, SetAccountTTL, GetAccountTTL, GetAuthorizations
from pyrogram.raw.types import UpdateUserName, UpdateUser, AccountDaysTTL

from tests.client import TestClient


@pytest.mark.asyncio
async def test_change_profile() -> None:
    async with TestClient(phone_number="123456789") as client:
        assert client.me

        async with client.expect_updates_m(UpdateUserName, UpdateUserName, UpdateUser):
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

        async with client.expect_updates_m(UpdateUserName):
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
        async with client.expect_updates_m(UpdateUserName):
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

        async with client.expect_updates_m(UpdateUserName):
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
        async with client2.expect_updates_m(UpdateUserName):
            await client2.set_username("test2_username")
        user2 = await client.get_users("test2_username")
        me2 = await client2.get_me()

        assert user2.id == me2.id


@pytest.mark.asyncio
async def test_check_username_invalid() -> None:
    async with TestClient(phone_number="123456789") as client:
        with pytest.raises(UsernameInvalid):
            await client.invoke(CheckUsername(username="a"))

        with pytest.raises(UsernameInvalid):
            await client.invoke(CheckUsername(username="a" * 100))

        with pytest.raises(UsernameInvalid):
            await client.invoke(CheckUsername(username="---------------"))


@pytest.mark.asyncio
async def test_check_username_occupied() -> None:
    async with TestClient(phone_number="123456789") as client:
        async with client.expect_updates_m(UpdateUserName):
            await client.set_username("test_username")

        with pytest.raises(UsernameOccupied):
            await client.invoke(CheckUsername(username="test_username"))


@pytest.mark.asyncio
async def test_check_username_success() -> None:
    async with TestClient(phone_number="123456789") as client:
        assert await client.invoke(CheckUsername(username="test_username"))


@pytest.mark.asyncio
async def test_change_username_to_another_one() -> None:
    async with TestClient(phone_number="123456789") as client, TestClient(phone_number="123456788") as client2:
        async with client.expect_updates_m(UpdateUserName):
            await client.set_username("test_username")

        with pytest.raises(UsernameOccupied):
            await client2.invoke(CheckUsername(username="test_username"))

        async with client.expect_updates_m(UpdateUserName):
            await client.set_username("test_username111")

        async with client2.expect_updates_m(UpdateUserName):
            await client2.set_username("test_username")


@pytest.mark.asyncio
async def test_unset_username() -> None:
    async with TestClient(phone_number="123456789") as client, TestClient(phone_number="123456788") as client2:
        async with client.expect_updates_m(UpdateUserName):
            await client.set_username("test_username")

        with pytest.raises(UsernameOccupied):
            await client2.invoke(CheckUsername(username="test_username"))

        async with client.expect_updates_m(UpdateUserName):
            await client.set_username(None)

        async with client2.expect_updates_m(UpdateUserName):
            await client2.set_username("test_username")


@pytest.mark.asyncio
async def test_get_set_account_ttl_success() -> None:
    async with TestClient(phone_number="123456789") as client:
        for ttl in (30, 60, 180, 365):
            assert await client.invoke(SetAccountTTL(ttl=AccountDaysTTL(days=ttl)))
            current_ttl = await client.invoke(GetAccountTTL())
            assert current_ttl.days == ttl


@pytest.mark.asyncio
async def test_set_account_ttl_invalid() -> None:
    async with TestClient(phone_number="123456789") as client:
        with pytest.raises(TtlDaysInvalid):
            await client.invoke(SetAccountTTL(ttl=AccountDaysTTL(days=1)))

        with pytest.raises(TtlDaysInvalid):
            await client.invoke(SetAccountTTL(ttl=AccountDaysTTL(days=400)))


@pytest.mark.asyncio
async def test_get_authorizations_one() -> None:
    async with TestClient(phone_number="123456789") as client:
        authorizations = await client.invoke(GetAuthorizations())
        assert authorizations
        assert len(authorizations.authorizations) == 1
        assert authorizations.authorizations[0].current
        assert authorizations.authorizations[0].hash == 0


@pytest.mark.asyncio
async def test_get_authorizations_multiple(exit_stack: AsyncExitStack) -> None:
    phone_number = "123456789"
    client = TestClient(phone_number=phone_number)
    await exit_stack.enter_async_context(client)

    for _ in range(10):
        await exit_stack.enter_async_context(TestClient(phone_number=phone_number))

    authorizations = await client.invoke(GetAuthorizations())
    assert authorizations
    assert len(authorizations.authorizations) == 11

    current = [auth for auth in authorizations.authorizations if auth.current]
    assert len(current) == 1
    assert current[0].hash == 0

    not_current = [auth for auth in authorizations.authorizations if not auth.current]
    assert all(auth.hash != 0 for auth in not_current)
