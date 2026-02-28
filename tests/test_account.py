import re
from contextlib import AsyncExitStack
from datetime import timedelta, datetime, UTC
from typing import cast

import pytest
from faker import Faker
from pyrogram.errors import UsernameInvalid, UsernameOccupied, UsernameNotModified, TtlDaysInvalid, AuthKeyUnregistered, \
    TwoFaConfirmWait, PasswordHashInvalid
from pyrogram.raw.functions.account import CheckUsername, SetAccountTTL, GetAccountTTL, GetAuthorizations, \
    DeleteAccount, GetPassword, SendConfirmPhoneCode, ConfirmPhone
from pyrogram.raw.types import UpdateUserName, UpdateUser, AccountDaysTTL, CodeSettings, UpdateNewMessage
from pyrogram.raw.types.auth import SentCode as TLSentCode
from pyrogram.utils import compute_password_check

from piltover.db.models import User, UserPassword, SentCode, PhoneCodePurpose, TaskIqScheduledDeleteUser
from tests.client import TestClient
from tests.conftest import ClientFactory, ClientFactorySync


@pytest.mark.asyncio
async def test_change_profile(client_with_auth: ClientFactory, exit_stack: AsyncExitStack) -> None:
    client: TestClient = await exit_stack.enter_async_context(await client_with_auth())

    assert client.me

    async with client.expect_updates_m(UpdateUserName, UpdateUserName, UpdateUser):
        assert await client.update_profile(first_name="test 123")
        assert await client.update_profile(last_name="test asd")
        assert await client.update_profile(bio="test bio")

    me = await client.get_me()

    assert me.first_name == "test 123"
    assert me.last_name == "test asd"


@pytest.mark.asyncio
async def test_change_username(client_with_auth: ClientFactory, exit_stack: AsyncExitStack) -> None:
    client: TestClient = await exit_stack.enter_async_context(await client_with_auth())

    async with client.expect_updates_m(UpdateUserName):
        assert await client.set_username("test_username")

    me = await client.get_me()
    assert me.username == "test_username"


@pytest.mark.asyncio
async def test_change_username_to_invalid(client_with_auth: ClientFactory, exit_stack: AsyncExitStack) -> None:
    client: TestClient = await exit_stack.enter_async_context(await client_with_auth())

    for username in ("tes/t_username", "very_long_username"*100, "username.with.dots", ".", ":::"):
        with pytest.raises(UsernameInvalid):
            assert await client.set_username(username)

        me = await client.get_me()
        assert me.username is None


@pytest.mark.asyncio
async def test_change_username_to_occupied(client_with_auth: ClientFactory, exit_stack: AsyncExitStack) -> None:
    client1: TestClient = await exit_stack.enter_async_context(await client_with_auth())
    client2: TestClient = await exit_stack.enter_async_context(await client_with_auth())

    async with client1.expect_updates_m(UpdateUserName):
        assert await client1.set_username("test_username")
    me = await client1.get_me()
    assert me.username == "test_username"

    with pytest.raises(UsernameOccupied):
        assert await client2.set_username("test_username")

        me = await client2.get_me()
        assert me.username is None


@pytest.mark.asyncio
async def test_change_username_to_same(client_with_auth: ClientFactory, exit_stack: AsyncExitStack) -> None:
    client: TestClient = await exit_stack.enter_async_context(await client_with_auth())

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
async def test_resolve_username(client_with_auth: ClientFactory, exit_stack: AsyncExitStack) -> None:
    client1: TestClient = await exit_stack.enter_async_context(await client_with_auth())
    client2: TestClient = await exit_stack.enter_async_context(await client_with_auth())

    async with client2.expect_updates_m(UpdateUserName):
        await client2.set_username("test2_username")
    user2 = await client1.get_users("test2_username")
    me2 = await client2.get_me()

    assert user2.id == me2.id


@pytest.mark.asyncio
async def test_check_username_invalid(client_with_auth: ClientFactory, exit_stack: AsyncExitStack) -> None:
    client: TestClient = await exit_stack.enter_async_context(await client_with_auth())

    with pytest.raises(UsernameInvalid):
        await client.invoke(CheckUsername(username="a"))

    with pytest.raises(UsernameInvalid):
        await client.invoke(CheckUsername(username="a" * 100))

    with pytest.raises(UsernameInvalid):
        await client.invoke(CheckUsername(username="---------------"))


@pytest.mark.asyncio
async def test_check_username_occupied(client_with_auth: ClientFactory, exit_stack: AsyncExitStack) -> None:
    client: TestClient = await exit_stack.enter_async_context(await client_with_auth())

    async with client.expect_updates_m(UpdateUserName):
        await client.set_username("test_username")

    with pytest.raises(UsernameOccupied):
        await client.invoke(CheckUsername(username="test_username"))


@pytest.mark.asyncio
async def test_check_username_success(client_with_auth: ClientFactory, exit_stack: AsyncExitStack) -> None:
    client: TestClient = await exit_stack.enter_async_context(await client_with_auth())
    assert await client.invoke(CheckUsername(username="test_username"))


@pytest.mark.asyncio
async def test_change_username_to_another_one(client_with_auth: ClientFactory, exit_stack: AsyncExitStack) -> None:
    client1: TestClient = await exit_stack.enter_async_context(await client_with_auth())
    client2: TestClient = await exit_stack.enter_async_context(await client_with_auth())

    async with client1.expect_updates_m(UpdateUserName):
        await client1.set_username("test_username")

    with pytest.raises(UsernameOccupied):
        await client2.invoke(CheckUsername(username="test_username"))

    async with client1.expect_updates_m(UpdateUserName):
        await client1.set_username("test_username111")

    async with client2.expect_updates_m(UpdateUserName):
        await client2.set_username("test_username")


@pytest.mark.asyncio
async def test_unset_username(client_with_auth: ClientFactory, exit_stack: AsyncExitStack) -> None:
    client1: TestClient = await exit_stack.enter_async_context(await client_with_auth())
    client2: TestClient = await exit_stack.enter_async_context(await client_with_auth())

    async with client1.expect_updates_m(UpdateUserName):
        await client1.set_username("test_username")

    with pytest.raises(UsernameOccupied):
        await client2.invoke(CheckUsername(username="test_username"))

    async with client1.expect_updates_m(UpdateUserName):
        await client1.set_username(None)

    async with client2.expect_updates_m(UpdateUserName):
        await client2.set_username("test_username")


@pytest.mark.asyncio
async def test_get_set_account_ttl_success(client_with_auth: ClientFactory, exit_stack: AsyncExitStack) -> None:
    client: TestClient = await exit_stack.enter_async_context(await client_with_auth())

    for ttl in (30, 60, 180, 365):
        assert await client.invoke(SetAccountTTL(ttl=AccountDaysTTL(days=ttl)))
        current_ttl = await client.invoke(GetAccountTTL())
        assert current_ttl.days == ttl


@pytest.mark.asyncio
async def test_set_account_ttl_invalid(client_with_auth: ClientFactory, exit_stack: AsyncExitStack) -> None:
    client: TestClient = await exit_stack.enter_async_context(await client_with_auth())

    with pytest.raises(TtlDaysInvalid):
        await client.invoke(SetAccountTTL(ttl=AccountDaysTTL(days=1)))

    with pytest.raises(TtlDaysInvalid):
        await client.invoke(SetAccountTTL(ttl=AccountDaysTTL(days=400)))


@pytest.mark.real_auth
@pytest.mark.asyncio
async def test_get_authorizations_one(exit_stack: AsyncExitStack, client_fake: ClientFactorySync) -> None:
    client: TestClient = await exit_stack.enter_async_context(client_fake())

    authorizations = await client.invoke(GetAuthorizations())
    assert authorizations
    assert len(authorizations.authorizations) == 1
    assert authorizations.authorizations[0].current
    assert authorizations.authorizations[0].hash == 0


@pytest.mark.asyncio
async def test_get_authorizations_multiple(exit_stack: AsyncExitStack, client_fake: ClientFactorySync) -> None:
    CLIENTS_COUNT = 10

    client: TestClient = await exit_stack.enter_async_context(client_fake())

    for _ in range(CLIENTS_COUNT):
        await exit_stack.enter_async_context(TestClient(phone_number=client.phone_number))

    authorizations = await client.invoke(GetAuthorizations())
    assert authorizations
    assert len(authorizations.authorizations) == CLIENTS_COUNT + 1

    current = [auth for auth in authorizations.authorizations if auth.current]
    assert len(current) == 1
    assert current[0].hash == 0

    not_current = [auth for auth in authorizations.authorizations if not auth.current]
    assert all(auth.hash != 0 for auth in not_current)


@pytest.mark.real_auth
@pytest.mark.asyncio
async def test_delete_account_without_password(client_fake: ClientFactorySync) -> None:
    client = client_fake()
    async with client:
        await client.invoke(DeleteAccount(reason="testing"))

    user = await User.get_or_none(id=client.me.id)
    assert user is not None
    assert user.deleted

    with pytest.raises(AuthKeyUnregistered):
        async with client:
            await client.get_me()


@pytest.mark.real_auth
@pytest.mark.asyncio
async def test_delete_account_password_modified_right_now(faker: Faker, client_fake: ClientFactorySync) -> None:
    client = client_fake()
    async with client:
        await client.enable_cloud_password(faker.password(12))
        await client.invoke(DeleteAccount(reason="testing"))

    user = await User.get_or_none(id=client.me.id)
    assert user is not None
    assert user.deleted

    with pytest.raises(AuthKeyUnregistered):
        async with client:
            await client.get_me()


@pytest.mark.real_auth
@pytest.mark.asyncio
async def test_delete_account_password_modified_last_year_nopassword(
        faker: Faker, client_fake: ClientFactorySync,
) -> None:
    client = client_fake()
    async with client:
        await client.enable_cloud_password(faker.password(12))
        await UserPassword.filter(user_id=client.me.id).update(modified_at=datetime.now(UTC) - timedelta(days=365))

        with pytest.raises(TwoFaConfirmWait):
            await client.invoke(DeleteAccount(reason="testing"))


@pytest.mark.real_auth
@pytest.mark.asyncio
async def test_delete_account_password_modified_last_year_wrong_password(
        faker: Faker, client_fake: ClientFactorySync,
) -> None:
    client = client_fake()
    password = faker.password(12)
    async with client:
        await client.enable_cloud_password(password)
        await UserPassword.filter(user_id=client.me.id).update(modified_at=datetime.now(UTC) - timedelta(days=365))

        with pytest.raises(PasswordHashInvalid):
            await client.invoke(DeleteAccount(
                reason="testing",
                password=compute_password_check(await client.invoke(GetPassword()), password + "1")
            ))


@pytest.mark.real_auth
@pytest.mark.asyncio
async def test_delete_account_password_modified_last_year_correct_password(
        faker: Faker, client_fake: ClientFactorySync,
) -> None:
    client = client_fake()
    password = faker.password(12)
    async with client:
        await client.enable_cloud_password(password)
        await UserPassword.filter(user_id=client.me.id).update(modified_at=datetime.now(UTC) - timedelta(days=365))

        await client.invoke(DeleteAccount(
            reason="testing",
            password=compute_password_check(await client.invoke(GetPassword()), password)
        ))

    user = await User.get_or_none(id=client.me.id)
    assert user is not None
    assert user.deleted

    with pytest.raises(AuthKeyUnregistered):
        async with client:
            await client.get_me()


CONFIRM_PATTERN = re.compile(r't.me/confirmphone\?phone=\d+&hash=([a-f0-9]+)')


@pytest.mark.real_auth
@pytest.mark.asyncio
async def test_delete_account_password_scheduled_cancel(
        exit_stack: AsyncExitStack, faker: Faker, client_fake: ClientFactorySync,
) -> None:
    client: TestClient = await exit_stack.enter_async_context(client_fake())

    await client.enable_cloud_password(faker.password(12))
    await UserPassword.filter(user_id=client.me.id).update(modified_at=datetime.now(UTC) - timedelta(days=365))

    with pytest.raises(TwoFaConfirmWait):
        await client.invoke(DeleteAccount(reason="testing"))

    await client.expect_update(UpdateNewMessage)

    assert TaskIqScheduledDeleteUser.filter(user_id=client.me.id).exists()

    confirm_message = [m async for m in client.get_chat_history(777000, limit=1)][0]
    confirm_hash = CONFIRM_PATTERN.findall(confirm_message.text)[0]

    sent = cast(TLSentCode, await client.invoke(SendConfirmPhoneCode(
        hash=confirm_hash,
        settings=CodeSettings(),
    )))

    await SentCode.filter(
        user_id=client.me.id, purpose=PhoneCodePurpose.CANCEL_ACCOUNT_DELETION
    ).update(code=123456)

    await client.invoke(ConfirmPhone(
        phone_code_hash=sent.phone_code_hash,
        phone_code="123456",
    ))

    assert TaskIqScheduledDeleteUser.filter(user_id=client.me.id).exists()
