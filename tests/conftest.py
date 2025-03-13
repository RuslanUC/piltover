from __future__ import annotations

import builtins
import hashlib
import logging
from os import urandom
from time import time
from typing import AsyncIterator

import pytest
import pytest_asyncio
from loguru import logger
from pyrogram import Client
from pyrogram.crypto import rsa
from pyrogram.crypto.rsa import PublicKey
from pyrogram.session import Auth
from pyrogram.session.internals import DataCenter
from pyrogram.storage import Storage
from pyrogram.storage.sqlite_storage import get_input_peer

from piltover.app.app import app
from piltover.db.models import AuthKey
from piltover.gateway import Gateway
from piltover.tl import Int
from piltover.utils import get_public_key_fingerprint


async def _custom_auth_create(_) -> bytes:
    key = urandom(256)
    key_id = Int.read_bytes(hashlib.sha1(key).digest()[-8:])
    await AuthKey.create(id=str(key_id), auth_key=key)
    return key


_real_auth_create = Auth.create


@pytest_asyncio.fixture(autouse=True)
async def app_server(request: pytest.FixtureRequest) -> AsyncIterator[Gateway]:
    async with app.run_test() as test_server:
        if request.node.name != "test_key_generation":
            Auth.create = _custom_auth_create

        print(f"Running on {test_server.port}")
        _setup_test_dc(test_server)

        yield test_server

        if request.node.name != "test_key_generation":
            Auth.create = _real_auth_create


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


def _setup_test_dc(server: Gateway) -> None:
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


class SimpleStorage(Storage):
    VERSION = 3
    USERNAME_TTL = 8 * 60 * 60

    def __init__(self, name: str):
        super().__init__(name)

        self._version = self.VERSION

        self._dc_id = None
        self._api_id = None
        self._test_mode = None
        self._auth_key = None
        self._date = None
        self._user_id = None
        self._is_bot = None

        self._peers_by_id = {}
        self._peers_by_username = {}
        self._peers_by_phone = {}

    def create(self):
        ...

    async def open(self):
        ...

    async def save(self):
        await self.date(int(time()))

    async def close(self):
       ...

    async def delete(self):
        self._version = self.VERSION

        self._dc_id = None
        self._api_id = None
        self._test_mode = None
        self._auth_key = None
        self._date = None
        self._user_id = None
        self._is_bot = None

        self._peers_by_id = {}
        self._peers_by_username = {}
        self._peers_by_phone = {}

    async def update_peers(self, peers: list[tuple[int, int, str, str, str]]):
        for peer in peers:
            peer_id, peer_hash, peer_type, username, phone_number = peer
            self._peers_by_id[peer_id] = (*peer, int(time()))
            if username:
                self._peers_by_username[username] = (*peer, int(time()))
            if phone_number:
                self._peers_by_phone[phone_number] = (*peer, int(time()))

    async def get_peer_by_id(self, peer_id: int):
        if peer_id not in self._peers_by_id:
            raise KeyError(f"ID not found: {peer_id}")

        peer_id, access_hash, peer_type, _, _, _ = self._peers_by_id[peer_id]
        return get_input_peer(peer_id, access_hash, peer_type)

    async def get_peer_by_username(self, username: str):
        if username not in self._peers_by_username:
            raise KeyError(f"Username not found: {username}")

        peer_id, access_hash, peer_type, _, _, updated_at = self._peers_by_username[username]
        if abs(time() - updated_at) > self.USERNAME_TTL:
            raise KeyError(f"Username expired: {username}")

        return get_input_peer(peer_id, access_hash, peer_type)

    async def get_peer_by_phone_number(self, phone_number: str):
        if phone_number not in self._peers_by_phone:
            raise KeyError(f"Phone number not found: {phone_number}")

        peer_id, access_hash, peer_type, _, _, _ = self._peers_by_phone[phone_number]
        return get_input_peer(peer_id, access_hash, peer_type)

    async def dc_id(self, value: int = object):
        if value == object:
            return self._dc_id
        else:
            self._dc_id = value

    async def api_id(self, value: int = object):
        if value == object:
            return self._api_id
        else:
            self._api_id = value

    async def test_mode(self, value: bool = object):
        if value == object:
            return self._test_mode
        else:
            self._test_mode = value

    async def auth_key(self, value: bytes = object):
        if value == object:
            return self._auth_key
        else:
            self._auth_key = value

    async def date(self, value: int = object):
        if value == object:
            return self._date
        else:
            self._date = value

    async def user_id(self, value: int = object):
        if value == object:
            return self._user_id
        else:
            self._user_id = value

    async def is_bot(self, value: bool = object):
        if value == object:
            return self._is_bot
        else:
            self._is_bot = value

    def version(self, value: int = object):
        if value == object:
            return self._version
        else:
            self._version = value


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

        self.storage = SimpleStorage(self.name)


def color_is_near(expected: tuple[int, int, int], actual: tuple[int, int, int], error: float = 0.05) -> bool:
    err_val = 0xff * error
    expected_min = (max(0x00, int(exp - err_val)) for exp in expected)
    expected_max = (min(0xff, int(exp + err_val)) for exp in expected)

    for exp_min, exp_max, act in zip(expected_min, expected_max, actual):
        if act < exp_min or act > exp_max:
            return False

    return True


# https://stackoverflow.com/a/72735401
class InterceptHandler(logging.Handler):
    _instance: InterceptHandler | None = None

    @logger.catch(default=True)
    def emit(self, record):
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno

        import sys
        frame, depth = sys._getframe(6), 6
        while frame and frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back
            depth += 1

        logger.opt(depth=depth, exception=record.exc_info).log(level, record.getMessage())

    @classmethod
    def redirect_to_loguru(cls, logger_name: str, level: int = logging.INFO) -> None:
        if not isinstance(cls._instance, cls):
            cls._instance = cls()

        std_logger = logging.getLogger(logger_name)
        std_logger.setLevel(level)
        std_logger.addHandler(cls._instance)


InterceptHandler.redirect_to_loguru("pyrogram")
InterceptHandler.redirect_to_loguru("aiocache.base", logging.DEBUG)
