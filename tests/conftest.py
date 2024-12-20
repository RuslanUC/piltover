import builtins

import pytest_asyncio
from pyrogram import Client
from pyrogram.crypto import rsa
from pyrogram.crypto.rsa import PublicKey
from pyrogram.session.internals import DataCenter

from piltover.app.__main__ import app
from piltover.high_level import Server
from piltover.utils import get_public_key_fingerprint


@pytest_asyncio.fixture(autouse=True)
async def app_server() -> Server:
    async with app.run_test() as test_server:
        print(f"Running on {test_server.port}")
        _setup_test_dc(test_server)

        yield test_server


class TestDataCenter(DataCenter):
    PORT: int

    def __new__(cls, dc_id: int, test_mode: bool, ipv6: bool, media: bool) -> tuple[str, int]:
        if test_mode:
            if ipv6:
                ip = cls.TEST_IPV6[dc_id]
            else:
                ip = cls.TEST[dc_id]

            return ip, cls.PORT
        else:
            if ipv6:
                if media:
                    ip = cls.PROD_IPV6_MEDIA.get(dc_id, cls.PROD_IPV6[dc_id])
                else:
                    ip = cls.PROD_IPV6[dc_id]
            else:
                if media:
                    ip = cls.PROD_MEDIA.get(dc_id, cls.PROD[dc_id])
                else:
                    ip = cls.PROD[dc_id]

            return ip, cls.PORT

    @classmethod
    def set_address(cls, host: str, port: int) -> None:
        cls.PORT = DataCenter.PORT = port

        for adresses in (cls.TEST, cls.PROD, cls.PROD_MEDIA):
            for dc_id, _ in adresses.items():
                adresses[dc_id] = host


def _setup_test_dc(server: Server) -> None:
    fingerprint = get_public_key_fingerprint(server.server_keys.public_key, signed=True)
    public_key = server.public_key.public_numbers()
    rsa.server_public_keys[fingerprint] = PublicKey(public_key.n, public_key.e)

    DataCenter.__new__ = TestDataCenter.__new__
    TestDataCenter.set_address(server.host, server.port)


real_input = input


def _input(prompt: str = "") -> str:
    if prompt == "Enter first name: ":
        return "Test"
    if prompt == "Enter last name (empty to skip): ":
        return "Last"

    return real_input(prompt)


builtins.input = _input


class TestClient(Client):
    def __init__(
            self,
            api_id: int = 12345,
            api_hash: str = "ff"*16,
            app_version: str = "0.0.0",
            device_model: str = "test_device",
            system_version: str = "1.0",
            lang_code: str = "en",
            bot_token: str = None,
            phone_number: str = None,
            phone_code: str = "2" * 5,
            password: str = None,
            workers: int = 2,
            no_updates: bool = None,
    ):
        super().__init__(
            name=":memory:",
            ipv6=False,
            proxy=None,
            test_mode=False,
            session_string=None,
            in_memory=True,
            plugins=None,
            takeout=None,
            hide_password=False,

            api_id=api_id,
            api_hash=api_hash,
            app_version=app_version,
            device_model=device_model,
            system_version=system_version,
            lang_code=lang_code,
            bot_token=bot_token,
            phone_number=phone_number,
            phone_code=phone_code,
            password=password,
            workers=workers,
            no_updates = no_updates,
        )
