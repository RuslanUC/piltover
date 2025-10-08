import hashlib
from os import urandom
from types import SimpleNamespace
from typing import cast

import pytest
from loguru import logger
from mtproto import ConnectionRole
from mtproto.packets import DecryptedMessagePacket
from pyrogram.raw.core import Message, TLObject
from pyrogram.raw.functions.auth import BindTempAuthKey
from pyrogram.raw.functions.help import GetCountriesList
from pyrogram.raw.types import BindAuthKeyInner
from pyrogram.raw.types.help import CountriesList, CountriesListNotModified
from pyrogram.session import Auth
from pyrogram.session.internals import MsgFactory
from tortoise.expressions import F

from piltover.db.models import TempAuthKey
from piltover.tl import Long
from tests.conftest import TestClient, TransportError


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


@pytest.mark.create_countries
@pytest.mark.asyncio
async def test_get_countries_list() -> None:
    async with TestClient(phone_number="123456789") as client:
        countries1: CountriesList = await client.invoke(GetCountriesList(lang_code="en", hash=0))
        assert len(countries1.countries) > 0
        assert countries1.hash != 0

        countries2: CountriesList = await client.invoke(GetCountriesList(lang_code="en", hash=0))
        assert countries1 == countries2

        countries3: CountriesList = await client.invoke(GetCountriesList(lang_code="en", hash=countries1.hash))
        assert isinstance(countries3, CountriesListNotModified)


async def _create_temp_auth_key() -> bytes:
    from pyrogram import raw

    class FakePQInnerData(raw.types.PQInnerDataTemp):
        def __init__(self, *args, **kwargs) -> None:
            super().__init__(*args, **kwargs, expires_in=86400)

    real_PQInnerData = raw.types.PQInnerData
    raw.types.PQInnerData = FakePQInnerData

    client_ = SimpleNamespace()
    setattr(client_, "ipv6", False)
    setattr(client_, "proxy", None)

    try:
        return cast(bytes, await Auth(cast(TestClient, client_), 2, False).create())
    finally:
        raw.types.PQInnerData = real_PQInnerData


async def _bind_temp_auth_key(temp_client: TestClient, temp_auth_key: bytes, perm_auth_key: bytes) -> None:
    temp_auth_key_id = Long.read_bytes(hashlib.sha1(temp_auth_key).digest()[-8:])
    perm_auth_key_id = Long.read_bytes(hashlib.sha1(perm_auth_key).digest()[-8:])

    await temp_client.storage.dc_id(2)
    await temp_client.storage.auth_key(temp_auth_key)
    await temp_client.storage.is_bot(False)
    await temp_client.storage.test_mode(False)
    await temp_client.storage.user_id(0)

    await temp_client.connect()
    session = temp_client.session

    old_msg_factory = session.msg_factory
    session.msg_factory = msg_factory = MsgFactoryCustom()
    msg_factory.seq_no = old_msg_factory.seq_no

    nonce = Long.read_bytes(urandom(8))
    session_id = Long.read_bytes(session.session_id)

    logger.info(f"Session id btw: {session_id}")
    logger.info(f"Perm auth key id btw: {perm_auth_key_id}")
    logger.info(f"Temp auth key id btw: {temp_auth_key_id}")

    inner_message = BindAuthKeyInner(
        nonce=nonce,
        temp_auth_key_id=temp_auth_key_id,
        perm_auth_key_id=perm_auth_key_id,
        temp_session_id=session_id,
        expires_at=0,
    )
    decrypted_message = DecryptedMessagePacket(
        salt=urandom(8),
        session_id=Long.read_bytes(urandom(8)),
        message_id=...,
        seq_no=0,
        data=inner_message.write(),
    )

    query = BindTempAuthKey(
        perm_auth_key_id=perm_auth_key_id,
        nonce=nonce,
        expires_at=0,
        encrypted_message=b"",
    )

    message_to_send = msg_factory(query)

    decrypted_message.message_id = message_to_send.msg_id
    encrypted_message = decrypted_message.encrypt(perm_auth_key, ConnectionRole.CLIENT, True)
    query.encrypted_message = encrypted_message.write()
    message_to_send.body = query
    message_to_send.length = len(query.write())

    assert await temp_client.invoke(message_to_send)

    await temp_client.disconnect()


class MsgFactoryCustom(MsgFactory):
    def __call__(self, body: TLObject | Message) -> Message:
        if isinstance(body, Message):
            return body
        return super().__call__(body)


@pytest.mark.real_key_gen
@pytest.mark.asyncio
async def test_temp_auth_key() -> None:
    auth_key_temp = await _create_temp_auth_key()

    perm_client = TestClient(phone_number="123456789")
    temp_client = TestClient(phone_number="123456789")

    async with perm_client:
        user_me = await perm_client.get_me()

    perm_auth_key = await perm_client.storage.auth_key()

    await _bind_temp_auth_key(temp_client, auth_key_temp, perm_auth_key)

    await temp_client.storage.user_id(user_me.id)
    async with temp_client:
        user_me_test = await temp_client.get_me()
        assert user_me_test.id == user_me.id


@pytest.mark.real_key_gen
@pytest.mark.asyncio
async def test_temp_auth_key_expired() -> None:
    auth_key_temp = await _create_temp_auth_key()
    temp_auth_key_id = Long.read_bytes(hashlib.sha1(auth_key_temp).digest()[-8:])

    perm_client = TestClient(phone_number="123456789")
    temp_client = TestClient(phone_number="123456789")

    async with perm_client:
        user_me = await perm_client.get_me()

    perm_auth_key = await perm_client.storage.auth_key()

    await _bind_temp_auth_key(temp_client, auth_key_temp, perm_auth_key)

    await temp_client.storage.user_id(user_me.id)
    async with temp_client:
        user_me_test = await temp_client.get_me()
        assert user_me_test.id == user_me.id

    await TempAuthKey.filter(id=temp_auth_key_id).update(expires_at=F("expires_at") - 86400 * 2)

    with pytest.raises(TransportError, check=lambda exc: exc.code == 404):
        async with temp_client:
            ...


@pytest.mark.real_key_gen
@pytest.mark.asyncio
async def test_temp_auth_key_expired_rebind() -> None:
    auth_key_temp = await _create_temp_auth_key()
    temp_auth_key_id = Long.read_bytes(hashlib.sha1(auth_key_temp).digest()[-8:])

    perm_client = TestClient(phone_number="123456789")
    temp_client = TestClient(phone_number="123456789")

    async with perm_client:
        user_me = await perm_client.get_me()

    perm_auth_key = await perm_client.storage.auth_key()

    await _bind_temp_auth_key(temp_client, auth_key_temp, perm_auth_key)

    await temp_client.storage.user_id(user_me.id)
    async with temp_client:
        user_me_test = await temp_client.get_me()
        assert user_me_test.id == user_me.id

    await TempAuthKey.filter(id=temp_auth_key_id).update(expires_at=F("expires_at") - 86400 * 2)

    with pytest.raises(TransportError, check=lambda exc: exc.code == 404):
        async with temp_client:
            ...

    auth_key_temp = await _create_temp_auth_key()
    await _bind_temp_auth_key(temp_client, auth_key_temp, perm_auth_key)

    await temp_client.storage.user_id(user_me.id)
    async with temp_client:
        user_me_test = await temp_client.get_me()
        assert user_me_test.id == user_me.id
