from __future__ import annotations

import argparse
import asyncio
import base64
import os
from contextlib import asynccontextmanager
from os import getenv
from pathlib import Path
from types import SimpleNamespace
from typing import Literal, AsyncIterator

import uvloop
from aerich import Command
from aerich.migrate import Migrate
from loguru import logger
from tortoise import Tortoise, connections

from piltover.app.handlers import register_handlers
from piltover.app.utils.app_create_system_data import create_system_data
from piltover.cache import Cache
from piltover.gateway import Gateway
from piltover.session_manager import SessionManager
from piltover.utils import gen_keys, get_public_key_fingerprint, Keys

DB_CONNECTION_STRING = getenv("DB_CONNECTION_STRING", "sqlite://data/secrets/piltover.db")


class ArgsNamespace(SimpleNamespace):
    data_dir: Path
    create_system_user: bool
    create_auth_countries: bool
    auth_countries_file: Path | None
    create_reactions: bool
    reactions_dir: Path | None
    create_chat_themes: bool
    chat_themes_dir: Path | None
    create_peer_colors: bool
    peer_colors_dir: Path | None
    create_languages: bool
    languages_dir: Path | None
    create_system_stickersets: bool
    system_stickersets_dir: Path | None
    create_emoji_groups: bool
    emoji_groups_dir: Path | None
    privkey_file: Path | None
    pubkey_file: Path | None
    rabbitmq_address: str | None
    redis_address: str | None
    cache_backend: Literal["memory", "redis", "memcached"]
    cache_endpoint: str | None
    cache_port: int | None

    def fill_defaults(self) -> None:
        if self.privkey_file is None:
            self.privkey_file = self.data_dir / "secrets" / "privkey.asc"
        if self.pubkey_file is None:
            self.pubkey_file = self.data_dir / "secrets" / "pubkey.asc"
        if self.auth_countries_file is None:
            self.auth_countries_file = self.data_dir / "auth_countries_list.json"
        if self.reactions_dir is None:
            self.reactions_dir = self.data_dir / "reactions"
        if self.chat_themes_dir is None:
            self.chat_themes_dir = self.data_dir / "chat_themes"
        if self.peer_colors_dir is None:
            self.peer_colors_dir = self.data_dir / "peer_colors"
        if self.languages_dir is None:
            self.languages_dir = self.data_dir / "languages"
        if self.system_stickersets_dir is None:
            self.system_stickersets_dir = self.data_dir / "stickersets"
        if self.emoji_groups_dir is None:
            self.emoji_groups_dir = self.data_dir / "emoji_groups"


class MigrateNoDowngrade(Migrate):
    @classmethod
    def diff_models(cls, old_models: dict[str, dict], new_models: dict[str, dict], upgrade=True, no_input=True) -> None:
        if not upgrade:
            return

        return super(MigrateNoDowngrade, cls).diff_models(old_models, new_models, True, no_input)


async def migrate():
    from os import environ
    migrations_dir = (args.data_dir / "migrations").absolute()

    command = Command({
        "connections": {"default": DB_CONNECTION_STRING},
        "apps": {"models": {"models": ["piltover.db.models", "aerich.models"], "default_connection": "default"}},
    }, location=str(migrations_dir))

    if environ.get("AERICH_RUN_FIX_MIGRATIONS", "").lower() in ("1", "true"):
        await command.fix_migrations()
    await command.init()

    if Path(migrations_dir).exists():
        await MigrateNoDowngrade.migrate("update", False)
        await command.upgrade(True)
    else:
        await command.init_db(True)

    await Tortoise.close_connections()


class PiltoverApp:
    def __init__(
            self, data_dir: Path, privkey: str | Path, pubkey: str | Path, host: str = "0.0.0.0", port: int = 4430,
            rabbitmq_address: str | None = None, redis_address: str | None = None, salt_key: str | None = None,
    ):
        self._host = host
        self._port = port

        privkey = Path(privkey)
        pubkey = Path(pubkey)
        if not (pubkey.exists() and privkey.exists()):
            pubkey.parent.mkdir(parents=True, exist_ok=True)
            privkey.parent.mkdir(parents=True, exist_ok=True)
            with privkey.open("w+") as priv, pubkey.open("w+") as pub:
                keys = gen_keys()
                priv.write(keys.private_key)
                pub.write(keys.public_key)

        self._private_key = privkey.read_text()
        self._public_key = pubkey.read_text()

        self._gateway = Gateway(
            data_dir=data_dir,
            host=host,
            port=port,
            server_keys=Keys(
                private_key=self._private_key,
                public_key=self._public_key,
            ),
            rabbitmq_address=rabbitmq_address,
            redis_address=redis_address,
            salt_key=base64.b64decode(salt_key) if salt_key is not None else None,
        )

        if self._gateway.worker is not None:
            register_handlers(self._gateway.worker)

    def _run_in_memory_scheduler(self) -> asyncio.Task | None:
        if self._gateway.scheduler is None:
            return None

        from taskiq.cli.scheduler.run import run_scheduler
        from taskiq.cli.scheduler.args import SchedulerArgs

        return asyncio.create_task(run_scheduler(
            SchedulerArgs(scheduler=self._gateway.scheduler.scheduler, modules=[])
        ))

    async def run(self, host: str | None = None, port: int | None = None):
        self._host = host or self._host
        self._port = port or self._port

        fp = get_public_key_fingerprint(self._public_key, signed=True)
        logger.info(
            "Pubkey fingerprint: {fp:x} ({no_sign})",
            fp=fp,
            no_sign=fp.to_bytes(8, "big", signed=True).hex(),
        )

        await migrate()

        await Tortoise.init(
            db_url=DB_CONNECTION_STRING,
            modules={"models": ["piltover.db.models"]},
        )

        await create_system_data(
            args, args.create_system_user, args.create_auth_countries, args.create_reactions, args.create_chat_themes,
            args.create_peer_colors, args.create_languages, args.create_system_stickersets, args.create_emoji_groups,
        )

        scheduler_task = self._run_in_memory_scheduler()

        logger.success(f"Running on {self._host}:{self._port}")
        await self._gateway.serve()
        await scheduler_task

    @asynccontextmanager
    async def run_test(
            self, create_sys_user: bool = True, create_countries: bool = False, create_reactions: bool = False,
            create_chat_themes: bool = False, create_peer_colors: bool = False, create_languages: bool = False,
            create_system_stickersets: bool = False, create_emoji_groups: bool = False, run_scheduler: bool = False,
    ) -> AsyncIterator[Gateway]:
        await Tortoise.init(
            db_url="sqlite://:memory:",
            modules={"models": ["piltover.db.models"]},
            _create_db=True,
        )
        await Tortoise.generate_schemas()
        await create_system_data(
            args,
            create_sys_user, create_countries, create_reactions, create_chat_themes, create_peer_colors,
            create_languages, create_system_stickersets, create_emoji_groups,
        )

        from piltover.app.handlers import testing
        if not testing.handler.registered:
            self._gateway.worker.register_handler(testing.handler)

        await self._gateway.broker.startup()

        scheduler_task = None
        if run_scheduler:
            scheduler_task = self._run_in_memory_scheduler()

        server = await asyncio.start_server(self._gateway.accept_client, "127.0.0.1", 0)
        async with server:
            self._gateway.host, self._gateway.port = server.sockets[0].getsockname()
            yield self._gateway

        if scheduler_task is not None:
            scheduler_task.cancel()
            await scheduler_task

        await self._gateway.broker.shutdown()
        await connections.close_all(True)
        await Cache.obj.clear()
        SessionManager.sessions.clear()


# TODO: add host and port to arguments
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", type=Path,
                        help="Path to data directory, where all files, server keys and other server data are stored.",
                        default=Path("./data"))
    parser.add_argument("--create-system-user", action="store_true", help="Create system user with id 777000")
    parser.add_argument("--create-auth-countries", action="store_true", help="Insert auth countries to database")
    parser.add_argument("--auth-countries-file", type=Path, default=None, help=(
        "Path to json file with auth countries (for --create-auth-countries option). "
        "By default, <data-dir>/auth_countries_list.json will be used."
    ))
    parser.add_argument("--create-reactions", action="store_true", help="Insert reactions to database")
    parser.add_argument("--reactions-dir", type=Path, default=None, help=(
        "Path to directory containing reactions files (for --create-reactions option). "
        "By default, <data-dir>/reactions will be used."
    ))
    parser.add_argument("--create-chat-themes", action="store_true", help="Insert chat themes to database")
    parser.add_argument("--chat-themes-dir", type=Path, default=None, help=(
        "Path to directory containing chat theme files (for --create-chat-themes option). "
        "By default, <data-dir>/chat_themes will be used."
    ))
    parser.add_argument("--create-peer-colors", action="store_true", help="Insert peer colors to database")
    parser.add_argument("--peer-colors-dir", type=Path, default=None, help=(
        "Path to directory containing peer colors files (for --create-peer-colors option). "
        "By default, <data-dir>/peer_colors will be used."
    ))
    parser.add_argument("--create-languages", action="store_true", help="Insert languages to database")
    parser.add_argument("--languages-dir", type=Path, default=None, help=(
        "Path to directory containing language files (for --create-languages option). "
        "By default, <data-dir>/languages will be used."
    ))
    parser.add_argument("--create-system-stickersets", action="store_true", help="Insert system stickersets into database")
    parser.add_argument("--system-stickersets-dir", type=Path, default=None, help=(
        "Path to directory containing stickerset files (for --create-system-stickersets option). "
        "By default, <data-dir>/stickersets will be used."
    ))
    parser.add_argument("--create-emoji-groups", action="store_true", help="Insert emoji groups into database")
    parser.add_argument("--emoji-groups-dir", type=Path, default=None, help=(
        "Path to directory containing emoji group files (for --create-emoji-groups option). "
        "By default, <data-dir>/emoji_groups will be used."
    ))
    parser.add_argument("--privkey-file", type=Path, default=None, help=(
        "Path to private key file. "
        "By default, <data-dir>/secrets/privkey.asc will be used."
        "Will be created if does not exist."
    ))
    parser.add_argument("--pubkey-file", type=Path, default=None, help=(
        "Path to public key file. "
        "By default, <data-dir>/secrets/pubkey.asc will be used."
        "Will be created if does not exist."
    ))
    parser.add_argument("--rabbitmq-address", type=str, required=False,
                        help="Address of rabbitmq server in \"amqp://user:password@host:port\" format",
                        default=None)
    parser.add_argument("--redis-address", type=str, required=False,
                        help="Address of redis server in \"redis://host:port\" format",
                        default=None)
    parser.add_argument("--cache-backend", type=str, required=False,
                        help="Cache backend", choices=["memory", "redis", "memcached"],
                        default="memory")
    parser.add_argument("--cache-endpoint", type=str, required=False,
                        help="Address of cache server (if \"cache-backend\" is \"redis\" or \"memcached\")",
                        default=None)
    parser.add_argument("--cache-port", type=int, required=False,
                        help="Port of cache server (if \"cache-backend\" is \"redis\" or \"memcached\")",
                        default=None)
    args = parser.parse_args(namespace=ArgsNamespace())
else:
    args = ArgsNamespace(
        create_system_user=True,
        create_auth_countries=True,
        auth_countries_file=Path("./data/auth_countries_list.json"),
        create_reactions=True,
        reactions_dir=Path("./data/reactions"),
        create_chat_themes=True,
        chat_themes_dir=Path("./data/chat_themes"),
        create_peer_colors=True,
        peer_colors_dir=Path("./data/peer_colors"),
        create_languages=True,
        languages_dir=Path("./data/languages"),
        create_system_stickersets=True,
        system_stickersets_dir=Path("./data/stickersets"),
        create_emoji_groups=True,
        emoji_groups_dir=Path("./data/emoji_groups"),
        data_dir=Path("./data") / "testing",
        privkey_file=None,
        pubkey_file=None,
        rabbitmq_address=None,
        redis_address=None,
        cache_backend="memory",
        cache_endpoint=None,
        cache_port=None,
    )

args.fill_defaults()


Cache.init(args.cache_backend, endpoint=args.cache_endpoint, port=args.cache_port)
app = PiltoverApp(
    data_dir=args.data_dir,
    privkey=args.privkey_file,
    pubkey=args.pubkey_file,
    rabbitmq_address=args.rabbitmq_address,
    redis_address=args.redis_address,
    # TODO: set via arg or store in "secrets" directory
    salt_key=os.environ.get("SALT_KEY", None),
)


if __name__ == "__main__":
    try:
        uvloop.install()
        asyncio.run(app.run())
    except KeyboardInterrupt:
        pass
