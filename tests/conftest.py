from __future__ import annotations

import asyncio
import builtins
import hashlib
import logging
import traceback
from asyncio import Task, DefaultEventLoopPolicy, CancelledError
from contextlib import AsyncExitStack
from os import urandom
from typing import AsyncIterator, TypeVar, TYPE_CHECKING, cast, Iterable, Callable, Coroutine, Awaitable
from unittest import mock

import pytest
import pytest_asyncio
from faker import Faker
from loguru import logger
from pyrogram.session import Auth
from taskiq import TaskiqScheduler
from taskiq.cli.scheduler.run import logger as taskiq_sched_logger
from tortoise import connections
from tortoise.backends.sqlite import SqliteClient
from tortoise.queryset import AwaitableQuery, BulkCreateQuery, BulkUpdateQuery, RawSQLQuery, ValuesQuery, \
    ValuesListQuery, CountQuery, DeleteQuery, UpdateQuery, QuerySet, ExistsQuery

from piltover.app_config import AppConfig
from piltover.db.enums import PeerType
from piltover.db.models import User, UserAuthorization, State, Peer
from piltover.exceptions import Unreachable
from piltover.utils.debug import measure_time_with_result
from piltover.worker import RequestHandler
from tests import server_instance, USE_REAL_TCP_FOR_TESTING, test_phone_number, skipping_auth
from tests.client import setup_test_dc, TestClient
from tests.scheduled_loop import run_scheduler_loop_every_100ms

if TYPE_CHECKING:
    from piltover.gateway import Gateway

T = TypeVar("T")


_real_real_auth_create = Auth.create


async def _Auth_init(self: Auth, client: TestClient, dc_id: int, test_mode: bool) -> None:
    self.dc_id = dc_id
    self.test_mode = test_mode
    self.ipv6 = client.ipv6
    self.proxy = client.proxy
    self.connection = None
    self.client = client


async def _real_auth_create(self: Auth) -> bytes:
    if not hasattr(self, "client"):
        return await _real_real_auth_create(self)
    if (key := getattr(self.client, "_generated_key", None)) is not None:
        return key

    return await _real_real_auth_create(self)


Auth.create = _real_auth_create


async def _custom_auth_create(self: Auth) -> bytes:
    from piltover.db.models import AuthKey
    from piltover.tl import Long

    key = urandom(256)
    key_id = Long.read_bytes(hashlib.sha1(key).digest()[-8:])
    auth_key = await AuthKey.create(id=key_id, auth_key=key)

    if not getattr(self, "_real_auth"):
        logger.trace("Skipping auth")
        user, created = await User.get_or_create(phone_number=test_phone_number.get(), defaults={
            "first_name": "First",
            "last_name": "Last",
        })
        if created:
            await State.create(user=user)
            await Peer.create(owner=user, type=PeerType.SELF, user=user)
        await UserAuthorization.create(user=user, key=auth_key, ip="0.0.0.0")

    return key


async def _empty_async_func(*args, **kwargs) -> None:
    ...


@pytest_asyncio.fixture(autouse=True)
async def app_server(request: pytest.FixtureRequest, pytestconfig: pytest.Config) -> AsyncIterator[Gateway]:
    from piltover.app.app import app, args

    marks = {mark.name for mark in request.node.own_markers}
    real_key_gen = "real_key_gen" in marks
    real_auth = "real_auth" in marks
    create_countries = "create_countries" in marks
    create_reactions = "create_reactions" in marks
    create_chat_themes = "create_chat_themes" in marks
    create_peer_colors = "create_peer_colors" in marks
    create_languages = "create_languages" in marks
    create_system_stickersets = "create_system_stickersets" in marks
    create_emoji_groups = "create_emoji_groups" in marks
    run_scheduler = "run_scheduler" in marks
    dont_create_sys_user = "dont_create_sys_user" in marks

    sched_insta_send_thresh = AppConfig.SCHEDULED_INSTANT_SEND_THRESHOLD
    AppConfig.SCHEDULED_INSTANT_SEND_THRESHOLD = -30

    async with AsyncExitStack() as stack:
        if run_scheduler:
            scheduler = cast(TaskiqScheduler, app._gateway.scheduler.scheduler)

            scheduler.startup = _empty_async_func
            scheduler.shutdown = _empty_async_func

            stack.enter_context(
                mock.patch("taskiq.cli.scheduler.run.run_scheduler_loop", run_scheduler_loop_every_100ms)
            )

        test_server: Gateway = await stack.enter_async_context(app.run_test(
            create_countries=create_countries, create_reactions=create_reactions, create_chat_themes=create_chat_themes,
            create_peer_colors=create_peer_colors, create_languages=create_languages,
            create_system_stickersets=create_system_stickersets, create_emoji_groups=create_emoji_groups,
            run_scheduler=run_scheduler, run_actual_server=USE_REAL_TCP_FOR_TESTING,
            create_sys_user=not dont_create_sys_user,
        ))

        server_reset_token = server_instance.set(test_server)
        skip_auth_reset_token = skipping_auth.set(not real_key_gen and not real_auth)

        if not real_key_gen:
            Auth.create = _custom_auth_create
            setattr(Auth, "_real_auth", real_auth)

        print(f"Running on {test_server.port}")
        setup_test_dc(test_server)

        yield test_server

        server_instance.reset(server_reset_token)
        skipping_auth.reset(skip_auth_reset_token)

        if not real_key_gen:
            Auth.create = _real_auth_create
            delattr(Auth, "_real_auth")

        if pytestconfig.getoption("--dump-db"):
            db_dumps_dir = args.data_dir / "test-database-dumps"
            db_dumps_dir.mkdir(parents=True, exist_ok=True)
            db_dump_file = db_dumps_dir / f"{request.node.name}.db"
            if db_dump_file.exists():
                db_dump_file.unlink()
            conn: SqliteClient = connections.get("default")
            await conn._connection.execute(f"vacuum main into '{db_dump_file}';")

    AppConfig.SCHEDULED_INSTANT_SEND_THRESHOLD = sched_insta_send_thresh


class QueryStats:
    def __init__(self) -> None:
        self.make_query_count = 0
        self.make_query_time = 0
        self.execute_count = 0
        self.execute_time = 0

    def reset(self) -> None:
        self.make_query_count = 0
        self.make_query_time = 0
        self.execute_count = 0
        self.execute_time = 0

    def add(self, stats: QueryStats) -> None:
        self.make_query_count += stats.make_query_count
        self.make_query_time += stats.make_query_time
        self.execute_count += stats.execute_count
        self.execute_time += stats.execute_time


def _patch_cls_replace_method(cls: type, names: Iterable[str], suffix: str, replace_with: Callable) -> None:
    for name in names:
        if not hasattr(cls, name):
            continue

        setattr(cls, f"{name}{suffix}", getattr(cls, name))
        setattr(cls, name, replace_with)
        return


def _unpatch_cls_replaced_method(cls: type, names: Iterable[str], suffix: str) -> None:
    for name in names:
        real_name = f"{name}{suffix}"
        if not hasattr(cls, real_name):
            continue

        setattr(cls, name, getattr(cls, real_name))
        delattr(cls, real_name)
        return


def _get_patched_cls_original_method(obj: object, names: Iterable[str], suffix: str) -> tuple[str, Callable]:
    for name in names:
        real_method = getattr(obj, f"{name}{suffix}", None)
        if real_method is not None:
            return name, real_method

    raise Unreachable


@pytest_asyncio.fixture(autouse=True)
async def measure_query_stats(request: pytest.FixtureRequest, pytestconfig: pytest.Config) -> AsyncIterator[None]:
    if not pytestconfig.getoption("--measure-queries"):
        yield
        return

    query_clss = [
        BulkCreateQuery, BulkUpdateQuery, RawSQLQuery, ValuesQuery, ValuesListQuery, CountQuery, ExistsQuery,
        DeleteQuery, UpdateQuery, QuerySet
    ]
    execute_methods = ("_execute", "_execute_many",)
    make_query_methods = ("_make_query", "_make_queries",)
    call_methods = ("__call__",)
    real_suffix = "_real"

    query_stats_test = QueryStats()
    query_stats = QueryStats()

    async def _RequestHandler___call__(self: RequestHandler, *args, **kwargs):
        _, _call_real = _get_patched_cls_original_method(self, call_methods, real_suffix)
        query_stats.reset()
        try:
            return await _call_real(*args, **kwargs)
        finally:
            query_stats_test.add(query_stats)
            logger.info(
                f"{self.func.__name__} made {query_stats.execute_count} ({query_stats.make_query_count}) queries "
                f"that took {query_stats.execute_count:.2f}ms ({query_stats.make_query_time:.2f}ms)"
            )

    _patch_cls_replace_method(RequestHandler, call_methods, real_suffix, _RequestHandler___call__)

    for cls in query_clss:
        async def _execute(self: AwaitableQuery, *args, **kwargs) -> ...:
            name, execute_real = _get_patched_cls_original_method(self, execute_methods, real_suffix)
            with measure_time_with_result(f"{self.__class__.__name__}.{name}()") as _time_spent:
                result = await execute_real(*args, **kwargs)

            query_stats.execute_count += 1
            query_stats.execute_time += await _time_spent

            return result

        def _make_query(self: AwaitableQuery, *args, **kwargs) -> ...:
            name, make_query_real = _get_patched_cls_original_method(self, make_query_methods, real_suffix)
            with measure_time_with_result(f"{self.__class__.__name__}.{name}()") as _time_spent:
                result = make_query_real(*args, **kwargs)

            query_stats.make_query_count += 1
            query_stats.make_query_time += _time_spent.result()

            return result

        _patch_cls_replace_method(cls, execute_methods, real_suffix, _execute)
        _patch_cls_replace_method(cls, make_query_methods, real_suffix, _make_query)

    yield

    for cls in query_clss:
        _unpatch_cls_replaced_method(cls, execute_methods, real_suffix)
        _unpatch_cls_replaced_method(cls, make_query_methods, real_suffix)

    _unpatch_cls_replaced_method(RequestHandler, call_methods, real_suffix)

    logger.info(
        f"Test {request.node.name} "
        f"made {query_stats_test.execute_count} ({query_stats_test.make_query_count}) queries "
        f"that took {query_stats_test.execute_count:.2f}ms ({query_stats_test.make_query_time:.2f}ms)"
    )


real_input = input
real_print = print


def _input(prompt: str = "") -> str:
    if prompt == "Enter first name: ":
        return "Test"
    if prompt == "Enter last name (empty to skip): ":
        return "Last"

    return real_input(prompt)


def _print(*args, **kwargs) -> None:
    hide = ["Pyrogram", "Code: ", "The confirmation code has been sent", "Running on "]

    if args and isinstance(args[0], str):
        for check in hide:
            if check in args[0]:
                return

    real_print(*args, **kwargs)


builtins.input = _input
builtins.print = _print


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
InterceptHandler.redirect_to_loguru("asyncio", logging.WARNING)
InterceptHandler.redirect_to_loguru("tg_secret.client", logging.DEBUG)


def _async_task_done_callback(task: Task) -> None:
    try:
        if task.exception() is not None:
            logger.opt(exception=task.exception()).error("Async task raised an exception")
    except CancelledError as e:
        logger.opt(exception=e).error("Async task was cancelled")


class _DebugTask(asyncio.Task):
    def cancel(self, *args, **kwargs) -> bool:
        stack = self.get_stack()
        if stack:
            formatted = "".join(traceback.format_stack())
            logger.error(f"Async task is being cancelled from:\n{formatted}")
        return super().cancel(*args, **kwargs)

    @classmethod
    def factory(cls, loop: asyncio.BaseEventLoop, coro: Coroutine, **kwargs) -> asyncio.Task:
        return cls(coro, loop=loop, **kwargs)


class CustomEventLoop(DefaultEventLoopPolicy._loop_factory):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.set_task_factory(_DebugTask.factory)

    def create_task(self, *args, **kwargs) -> Task:
        task: Task = super().create_task(*args, **kwargs)
        task.add_done_callback(_async_task_done_callback)
        return task


class CustomEventLoopPolicy(DefaultEventLoopPolicy):
    _loop_factory = CustomEventLoop


@pytest.fixture(scope="session")
def event_loop_policy():
    return CustomEventLoopPolicy()


@pytest_asyncio.fixture(autouse=True)
async def exit_stack(request: pytest.FixtureRequest) -> AsyncIterator[AsyncExitStack]:
    async with AsyncExitStack() as stack:
        yield stack


def pytest_addoption(parser: pytest.Parser):
    parser.addoption(
        "--dump-db", action="store_true", default=False, help="dump database at the end of each test to a file",
    )
    parser.addoption(
        "--measure-queries", action="store_true", default=False,
        help="measure db queries counts and timings per request handler and per test"
    )
    parser.addoption(
        "--faker-seed", default=42,
        help="random seed for generating fake test data"
    )


@pytest.fixture()
def faker(pytestconfig: pytest.Config) -> Faker:
    faker_inst = Faker()
    faker_inst.seed_instance(pytestconfig.getoption("--dump-db"))
    return faker_inst


ClientFactory = Callable[[str], Awaitable[TestClient]] | Callable[[], Awaitable[TestClient]]
ClientFactorySync = Callable[[str], TestClient] | Callable[[], TestClient]


@pytest_asyncio.fixture()
async def client_fake(faker: Faker) -> ClientFactorySync:
    def _create_client(phone_number: str | None = None) -> TestClient:
        if phone_number is None:
            phone_number = faker.msisdn()

        return TestClient(
            phone_number=phone_number,
            first_name=faker.first_name(),
            last_name=faker.last_name(),
        )

    return _create_client


@pytest_asyncio.fixture()
async def client_with_key(client_fake: ClientFactorySync) -> ClientFactory:
    from piltover.db.models import AuthKey, User, State, Peer
    from piltover.tl import Long

    async def _create_client_with_key(phone_number: str | None = None) -> TestClient:
        key = urandom(256)
        key_id = Long.read_bytes(hashlib.sha1(key).digest()[-8:])
        await AuthKey.create(id=key_id, auth_key=key)

        client = client_fake(phone_number)

        user, created = await User.get_or_create(phone_number=client.phone_number, defaults={
            "first_name": client.first_name,
            "last_name": client.last_name,
        })
        if created:
            await State.create(user=user)
            await Peer.create(owner=user, type=PeerType.SELF, user=user)

        setattr(client, "_generated_key", key)
        return client

    return _create_client_with_key


@pytest_asyncio.fixture()
async def client_with_auth(client_with_key: ClientFactory) -> ClientFactory:
    from piltover.db.models import AuthKey
    from piltover.tl import Long

    async def _create_client_with_auth(phone_number: str | None = None) -> TestClient:
        client = await client_with_key(phone_number)
        user = await User.get(phone_number=client.phone_number)
        key_id = Long.read_bytes(hashlib.sha1(getattr(client, "_generated_key")).digest()[-8:])
        auth_key = await AuthKey.get(id=key_id)
        await UserAuthorization.create(user=user, key=auth_key, ip="0.0.0.0")
        return client

    return _create_client_with_auth
