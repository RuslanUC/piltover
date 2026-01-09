from __future__ import annotations

from asyncio import Event, Lock, timeout
from collections import defaultdict
from contextlib import asynccontextmanager
from io import BytesIO
from time import time
from typing import TypeVar, Self, TYPE_CHECKING

from loguru import logger
from pyrogram import Client
from pyrogram.crypto import rsa
from pyrogram.crypto.rsa import PublicKey
from pyrogram.raw.base import InputPrivacyKey
from pyrogram.raw.core import TLObject as PyroTLObject
from pyrogram.raw.functions import InvokeWithLayer
from pyrogram.raw.functions.account import SetPrivacy
from pyrogram.raw.types import Updates, InputPrivacyKeyAddedByPhone, InputPrivacyKeyChatInvite, InputPrivacyKeyForwards, \
    InputPrivacyKeyPhoneNumber, InputPrivacyKeyPhoneCall, InputPrivacyKeyProfilePhoto, InputPrivacyKeyStatusTimestamp, \
    InputPrivacyKeyVoiceMessages, InputPrivacyKeyPhoneP2P, InputPrivacyValueAllowAll, InputPrivacyValueAllowUsers, \
    InputPrivacyValueDisallowChatParticipants, InputPrivacyValueDisallowUsers, InputPrivacyValueDisallowContacts, \
    InputPrivacyValueDisallowAll, InputPrivacyValueAllowChatParticipants, InputPrivacyValueAllowContacts, UpdateShort, \
    UpdatesCombined
from pyrogram.session import Session as PyroSession
from pyrogram.session.internals import DataCenter
from pyrogram.storage import Storage
from pyrogram.storage.sqlite_storage import get_input_peer
from pyrogram.types import User

from piltover.utils.debug import measure_time

if TYPE_CHECKING:
    from piltover.gateway import Gateway
    from piltover.tl import TLRequest


T = TypeVar("T")
InputPrivacyKey = InputPrivacyKeyAddedByPhone | InputPrivacyKeyChatInvite | InputPrivacyKeyForwards \
                  | InputPrivacyKeyPhoneCall | InputPrivacyKeyPhoneNumber | InputPrivacyKeyPhoneP2P \
                  | InputPrivacyKeyProfilePhoto | InputPrivacyKeyStatusTimestamp | InputPrivacyKeyVoiceMessages
InputPrivacyRule = InputPrivacyValueAllowAll | InputPrivacyValueAllowChatParticipants | InputPrivacyValueAllowContacts \
                   | InputPrivacyValueAllowUsers | InputPrivacyValueDisallowAll \
                   | InputPrivacyValueDisallowChatParticipants | InputPrivacyValueDisallowContacts \
                   | InputPrivacyValueDisallowUsers




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


def setup_test_dc(server: Gateway) -> None:
    from piltover.utils import get_public_key_fingerprint

    fingerprint = get_public_key_fingerprint(server.server_keys.public_key, signed=True)
    public_key = server.public_key.public_numbers()
    rsa.server_public_keys[fingerprint] = PublicKey(public_key.n, public_key.e)

    DataCenter.__new__ = TestDataCenter.__new__
    TestDataCenter.set_address(server.host, server.port)


class TransportError(RuntimeError):
    def __init__(self, error_code: int) -> None:
        super().__init__(f"Got transport error {error_code}")
        self.code = error_code


async def _session_recv_worker(self: PyroSession):
    from piltover.tl.primitives import Int
    from pyrogram.session.session import log
    log.info("NetworkTask started")

    while True:
        packet = await self.connection.recv()

        if packet is None or len(packet) == 4:
            if packet:
                error_code = -Int.read_bytes(packet)
                log.warning(
                    "Server sent transport error: %s (%s)",
                    error_code, PyroSession.TRANSPORT_ERRORS.get(error_code, "unknown error")
                )

                if error_code == 404:
                    raise TransportError(404)

            if self.is_started.is_set():
                self.loop.create_task(self.restart())

            break

        self.loop.create_task(self.handle_packet(packet))

    log.info("NetworkTask stopped")


PyroSession.recv_worker = _session_recv_worker
PyroSession.MAX_RETRIES = 2


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
            no_updates=no_updates,
        )

        self.storage = SimpleStorage(self.name)
        self._got_updates: dict[type[T], list[T]] = defaultdict(list)
        self._updates_event = Event()
        self._updates_lock = Lock()

    async def __aenter__(self) -> Self:
        self._got_updates = defaultdict(list)
        return await super().__aenter__()

    async def __aexit__(self, *args) -> None:
        unconsumed_updates = []
        for updates in self._got_updates.values():
            unconsumed_updates.extend(updates)
        if unconsumed_updates:
            logger.warning(f"Unexpected updates:")
            for update in unconsumed_updates:
                logger.warning(f"  {update}")

        return await super().__aexit__(*args)

    async def handle_updates(self, updates: PyroTLObject, only_add: bool = False) -> ...:
        if isinstance(updates, (Updates, UpdatesCombined)):
            _updates = updates.updates
        elif isinstance(updates, UpdateShort):
            _updates = [updates.update]
        else:
            _updates = updates

        async with self._updates_lock:
            for update in _updates:
                logger.trace(f"Got update btw: {update}")
                self._got_updates[type(update)].append(update)

        self._updates_event.set()

        if not only_add:
            return await super().handle_updates(updates)

    async def invoke(
            self, query: PyroTLObject, retries: int = PyroSession.MAX_RETRIES,
            timeout: float = PyroSession.WAIT_TIMEOUT, sleep_threshold: float = None,
    ) -> PyroTLObject:
        with measure_time("<pyrogram>.invoke(...)"):
            res = await super().invoke(query, retries, timeout, sleep_threshold)
        if isinstance(res, Updates):
            with measure_time("<pyrogram>.handle_updates(...)"):
                await self.handle_updates(res, True)
        return res

    async def invoke_p(self, query: TLRequest[T], with_layer: int | None = None) -> T:
        pyro_query = PyroTLObject.read(BytesIO(query.write()))
        if with_layer:
            pyro_query = InvokeWithLayer(layer=with_layer, query=pyro_query)
        return await self.invoke(pyro_query)

    async def expect_update(self, update_cls: type[T], timeout_: float = 1) -> T:
        async with timeout(timeout_):
            while True:
                async with self._updates_lock:
                    if self._got_updates[update_cls]:
                        return self._got_updates[update_cls].pop(0)

                await self._updates_event.wait()
                self._updates_event.clear()

    async def expect_updates(
            self, *update_clss: type[PyroTLObject], timeout_per_update: float = 0.5,
    ) -> list[PyroTLObject]:
        result = []
        for update_cls in update_clss:
            result.append(await self.expect_update(update_cls, timeout_per_update))
        return result

    @asynccontextmanager
    async def expect_updates_m(self, *update_clss: type[PyroTLObject], timeout_per_update: float = 0.5) -> ...:
        yield
        await self.expect_updates(*update_clss, timeout_per_update=timeout_per_update)

    async def authorize(self) -> User:
        with measure_time("authorize()"):
            return await super().authorize()

    async def connect(self) -> bool:
        with measure_time("connect()"):
            return await super().connect()

    async def start(self) -> bool:
        with measure_time("start()"):
            return await super().start()

    async def set_privacy(self, key: InputPrivacyKey, rules: InputPrivacyRule | list[InputPrivacyRule]) -> None:
        if not isinstance(rules, list):
            rules = [rules]

        await self.invoke(SetPrivacy(key=key, rules=rules))
