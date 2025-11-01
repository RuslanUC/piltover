from __future__ import annotations

import asyncio
import builtins
import hashlib
import logging
from asyncio import Event, Lock, timeout, Task, DefaultEventLoopPolicy
from collections import defaultdict
from contextlib import asynccontextmanager, AsyncExitStack
from io import BytesIO
from os import urandom
from time import time
from typing import AsyncIterator, TypeVar, Self, TYPE_CHECKING, cast
from unittest import mock

import pytest
import pytest_asyncio
from loguru import logger
from pyrogram import Client
from pyrogram.crypto import rsa
from pyrogram.crypto.rsa import PublicKey
from pyrogram.raw.core import TLObject as PyroTLObject
from pyrogram.raw.functions import InvokeWithLayer
from pyrogram.raw.types import Updates
from pyrogram.session import Auth, Session as PyroSession
from pyrogram.session.internals import DataCenter
from pyrogram.storage import Storage
from pyrogram.storage.sqlite_storage import get_input_peer
from taskiq import TaskiqScheduler
from taskiq.cli.scheduler.run import logger as taskiq_sched_logger

from piltover.app_config import AppConfig

if TYPE_CHECKING:
    from piltover.gateway import Gateway
    from piltover.tl import TLRequest


T = TypeVar("T")


async def _custom_auth_create(_) -> bytes:
    from piltover.db.models import AuthKey
    from piltover.tl import Long

    key = urandom(256)
    key_id = Long.read_bytes(hashlib.sha1(key).digest()[-8:])
    await AuthKey.create(id=key_id, auth_key=key)
    return key


_real_auth_create = Auth.create


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


async def _empty_async_func(*args, **kwargs) -> None:
    ...


@pytest_asyncio.fixture(autouse=True)
async def app_server(request: pytest.FixtureRequest) -> AsyncIterator[Gateway]:
    from piltover.app.app import app

    marks = {mark.name for mark in request.node.own_markers}
    real_key_gen = "real_key_gen" in marks
    create_countries = "create_countries" in marks
    create_reactions = "create_reactions" in marks
    create_chat_themes = "create_chat_themes" in marks
    create_peer_colors = "create_peer_colors" in marks
    run_scheduler = "run_scheduler" in marks

    sched_insta_send_thresh = AppConfig.SCHEDULED_INSTANT_SEND_THRESHOLD
    AppConfig.SCHEDULED_INSTANT_SEND_THRESHOLD = -30

    async with AsyncExitStack() as stack:
        if run_scheduler:
            scheduler = cast(TaskiqScheduler, app._gateway.scheduler.scheduler)

            scheduler.startup = _empty_async_func
            scheduler.shutdown = _empty_async_func

            stack.enter_context(
                mock.patch("taskiq.cli.scheduler.run.run_scheduler_loop", _run_scheduler_loop_every_100ms)
            )

        test_server = await stack.enter_async_context(app.run_test(
            create_countries=create_countries, create_reactions=create_reactions, create_chat_themes=create_chat_themes,
            create_peer_colors=create_peer_colors, run_scheduler=run_scheduler,
        ))

        if not real_key_gen:
            Auth.create = _custom_auth_create

        print(f"Running on {test_server.port}")
        _setup_test_dc(test_server)

        yield test_server

        if not real_key_gen:
            Auth.create = _real_auth_create

    AppConfig.SCHEDULED_INSTANT_SEND_THRESHOLD = sched_insta_send_thresh


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
    from piltover.utils import get_public_key_fingerprint

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
        if isinstance(updates, Updates):
            _updates = updates.updates
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
        res = await super().invoke(query, retries, timeout, sleep_threshold)
        if isinstance(res, Updates):
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
            self, *update_clss: type[PyroTLObject], timeout_per_update: float = 0.5
    ) -> list[PyroTLObject]:
        result = []
        for update_cls in update_clss:
            result.append(await self.expect_update(update_cls, timeout_per_update))
        return result

    @asynccontextmanager
    async def expect_updates_m(self, *update_clss: type[PyroTLObject], timeout_per_update: float = 0.5) -> ...:
        yield
        await self.expect_updates(*update_clss, timeout_per_update=timeout_per_update)


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
InterceptHandler.redirect_to_loguru("taskiq", logging.WARNING)
InterceptHandler.redirect_to_loguru(taskiq_sched_logger.name, logging.DEBUG)


def _async_task_done_callback(task: Task) -> None:
    if task.exception() is not None:
        logger.opt(exception=task.exception()).error("Async task raised an exception")


class CustomEventLoop(DefaultEventLoopPolicy._loop_factory):
    def create_task(self, *args, **kwargs) -> Task:
        task: Task = super().create_task(*args, **kwargs)
        task.add_done_callback(_async_task_done_callback)
        return task


class CustomEventLoopPolicy(DefaultEventLoopPolicy):
    _loop_factory = CustomEventLoop


@pytest.fixture(scope="session")
def event_loop_policy(request):
    return CustomEventLoopPolicy()


@pytest_asyncio.fixture(autouse=True)
async def exit_stack(request: pytest.FixtureRequest) -> AsyncIterator[AsyncExitStack]:
    async with AsyncExitStack() as stack:
        yield stack


async def _run_scheduler_loop_every_100ms(scheduler: TaskiqScheduler) -> None:
    from taskiq.cli.scheduler.run import get_all_schedules, get_task_delay, delayed_send, logger as taskiq_logger

    logger.debug("Starting taskiq scheduler")

    loop = asyncio.get_event_loop()
    while True:
        scheduled_tasks = await get_all_schedules(scheduler)
        logger.trace(f"Got {len(scheduled_tasks)} scheduled tasks")
        for source, task_list in scheduled_tasks.items():
            for task in task_list:
                try:
                    task_delay = get_task_delay(task)
                except ValueError:
                    taskiq_logger.warning(
                        "Cannot parse cron: %s for task: %s, schedule_id: %s",
                        task.cron,
                        task.task_name,
                        task.schedule_id,
                    )
                    continue
                logger.trace(f"Task delay is {task_delay} seconds")
                if task_delay is not None:
                    loop.create_task(delayed_send(scheduler, source, task, task_delay))
        await asyncio.sleep(.25)
