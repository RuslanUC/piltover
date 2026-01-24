from __future__ import annotations

import builtins
import hashlib
import logging
from asyncio import Task, DefaultEventLoopPolicy
from contextlib import AsyncExitStack
from os import urandom
from typing import AsyncIterator, TypeVar, TYPE_CHECKING, cast
from unittest import mock

import pytest
import pytest_asyncio
from loguru import logger
from pyrogram.session import Auth
from taskiq import TaskiqScheduler
from taskiq.cli.scheduler.run import logger as taskiq_sched_logger
from tortoise.queryset import AwaitableQuery, BulkCreateQuery, BulkUpdateQuery, RawSQLQuery, ValuesQuery, \
    ValuesListQuery, CountQuery, DeleteQuery, UpdateQuery, QuerySet, ExistsQuery

from piltover.app_config import AppConfig
from piltover.db.models import User, UserAuthorization
from piltover.utils.debug import measure_time
from tests import server_instance, USE_REAL_TCP_FOR_TESTING, test_phone_number, skipping_auth
from tests.client import setup_test_dc
from tests.scheduled_loop import run_scheduler_loop_every_100ms

if TYPE_CHECKING:
    from piltover.gateway import Gateway

T = TypeVar("T")


async def _custom_auth_create(self: Auth) -> bytes:
    from piltover.db.models import AuthKey
    from piltover.tl import Long

    key = urandom(256)
    key_id = Long.read_bytes(hashlib.sha1(key).digest()[-8:])
    auth_key = await AuthKey.create(id=key_id, auth_key=key)

    if not getattr(self, "_real_auth"):
        logger.trace("Skipping auth")
        user, _ = await User.get_or_create(phone_number=test_phone_number.get(), defaults={
            "first_name": "First",
            "last_name": "Last",
        })
        await UserAuthorization.create(user=user, key=auth_key, ip="0.0.0.0")

    return key


_real_auth_create = Auth.create


async def _empty_async_func(*args, **kwargs) -> None:
    ...


@pytest_asyncio.fixture(autouse=True)
async def app_server(request: pytest.FixtureRequest) -> AsyncIterator[Gateway]:
    # loop = get_running_loop()
    # loop.set_debug(True)
    # loop.slow_callback_duration = 0.01

    query_clss = [
        BulkCreateQuery, BulkUpdateQuery, RawSQLQuery, ValuesQuery, ValuesListQuery, CountQuery, ExistsQuery,
        DeleteQuery, UpdateQuery, QuerySet
    ]

    for cls in query_clss:
        async def _execute(self: AwaitableQuery, *args, **kwargs) -> None:
            _execute_real = getattr(self, "_execute_real")
            with measure_time(f"{self.__class__.__name__}._execute()"):
                return await _execute_real(*args, **kwargs)

        setattr(cls, "_execute_real", getattr(cls, "_execute"))
        setattr(cls, "_execute", _execute)

    from piltover.app.app import app

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

    AppConfig.SCHEDULED_INSTANT_SEND_THRESHOLD = sched_insta_send_thresh

    for cls in query_clss:
        _execute_real = getattr(cls, "_execute_real")
        setattr(cls, "_execute", _execute_real)
        delattr(cls, "_execute_real")


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
def event_loop_policy():
    return CustomEventLoopPolicy()


@pytest_asyncio.fixture(autouse=True)
async def exit_stack(request: pytest.FixtureRequest) -> AsyncIterator[AsyncExitStack]:
    async with AsyncExitStack() as stack:
        yield stack


#@pytest_asyncio.fixture(scope="session", autouse=True)
#async def profile_tests() -> ...:
#    import yappi
#
#    yappi.set_clock_type("wall")
#    yappi.start()
#
#    yield
#
#    yappi.stop()
#    stats = yappi.get_func_stats()
#    stats.print_all()
