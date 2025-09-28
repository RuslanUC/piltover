from __future__ import annotations

import argparse
import asyncio
from contextlib import asynccontextmanager
from os import getenv
from pathlib import Path
from types import SimpleNamespace
from typing import Literal, AsyncIterator, TYPE_CHECKING, Any
from uuid import UUID

import uvloop
from aerich import Command, Migrate
from fastrand import xorshift128plus_bytes
from loguru import logger
from tortoise import Tortoise, connections
from tortoise.expressions import Q

from piltover.app.handlers import register_handlers
from piltover.app_config import AppConfig
from piltover.cache import Cache
from piltover.gateway import Gateway
from piltover.tl import Long
from piltover.utils import gen_keys, get_public_key_fingerprint, Keys

if TYPE_CHECKING:
    from piltover.db.models import File

DB_CONNECTION_STRING = getenv("DB_CONNECTION_STRING", "sqlite://data/secrets/piltover.db")


class ArgsNamespace(SimpleNamespace):
    data_dir: Path
    create_system_user: bool
    create_auth_countries: bool
    auth_countries_file: Path | None
    create_reactions: bool
    reactions_dir: Path | None
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


class MigrateNoDowngrade(Migrate):
    @classmethod
    def diff_models(cls, old_models: dict[str, dict], new_models: dict[str, dict], upgrade=True, no_input=True) -> None:
        if not upgrade:
            return

        return super(MigrateNoDowngrade, cls).diff_models(old_models, new_models, True, no_input)


async def _upload_reaction_doc(reaction: int, doc: dict) -> File:
    from datetime import datetime
    from pytz import UTC

    from piltover.tl.types import DocumentAttributeImageSize, DocumentAttributeSticker, DocumentAttributeFilename
    from piltover.db.models import File
    from piltover.db.enums import FileType
    from piltover.app.utils.utils import PHOTOSIZE_TO_INT

    cls_name_to_cls = {
        "types.DocumentAttributeImageSize": DocumentAttributeImageSize,
        "types.DocumentAttributeSticker": DocumentAttributeSticker,
        "types.DocumentAttributeFilename": DocumentAttributeFilename,
    }

    ext = doc["mime_type"].split("/")[-1]
    reactions_files = args.reactions_dir / "files"

    photo_path = None
    for thumb in doc["thumbs"]:
        if thumb["_"] != "types.PhotoPathSize" or thumb["_"] != "j":
            continue
        with open(reactions_files / f"{doc['id']}-{reaction}-thumb-j.bin", "rb") as f:
            photo_path = f.read()
        break

    # TODO: dont create new file if it already exists
    file = File(
        created_at=datetime.fromtimestamp(doc["date"], UTC),
        mime_type=doc["mime_type"],
        size=doc["size"],
        type=FileType.DOCUMENT_STICKER,
        photo_path=photo_path,
        photo_sizes=[],
        constant_access_hash=Long.read_bytes(xorshift128plus_bytes(8)),
        constant_file_ref=UUID(bytes=xorshift128plus_bytes(16)),
    )
    await file.parse_attributes_from_tl([
        cls_name_to_cls[attr.pop("_")](**attr)
        for attr in doc["attributes"]
    ])
    await file.save()

    files_dir = args.data_dir / "files"

    with open(reactions_files / f"{doc['id']}-{reaction}.{ext}", "rb") as f_in:
        with open(files_dir / f"{file.physical_id}", "wb") as f_out:
            f_out.write(f_in.read())

    for thumb in doc["thumbs"]:
        if thumb["_"] != "types.PhotoSize":
            continue
        width = PHOTOSIZE_TO_INT[thumb["type"]]
        with open(reactions_files / f"{doc['id']}-{reaction}-thumb-{thumb['type']}.{ext}", "rb") as f_in:
            with open(files_dir / f"{file.physical_id}_{width}", "wb") as f_out:
                f_out.write(f_in.read())

        file.photo_sizes.append({
            "type_": thumb["type"],
            "w": thumb["w"],
            "h": thumb["h"],
            "size": thumb["size"],
        })

    await file.save(update_fields=["photo_sizes"])

    return file


async def _create_system_data(system_users: bool = True, countries_list: bool = True, reactions: bool = True) -> None:
    if system_users:
        logger.info("Creating system user...")

        from piltover.db.models import User, Username
        sys_user, _ = await User.update_or_create(id=777000, defaults={
            "phone_number": "42777",
            "first_name": AppConfig.NAME,
        })
        await Username.filter(Q(user=sys_user) | Q(username=AppConfig.SYS_USER_USERNAME)).delete()
        await Username.create(user=sys_user, username=AppConfig.SYS_USER_USERNAME)

        test_bot = await User.get_or_none(usernames__username="test_bot")
        if test_bot is None:
            test_bot = await User.create(phone_number=None, first_name="Test Bot", bot=True)
        else:
            test_bot.phone_number = None
            test_bot.first_name = "Test Bot"
            test_bot.bot = True
            await test_bot.save(update_fields=["phone_number", "first_name", "bot"])
        await Username.filter(Q(user=test_bot) | Q(username="test_bot")).delete()
        await Username.create(user=test_bot, username="test_bot")

    if countries_list and args.auth_countries_file.exists():
        logger.info("Creating auth countries...")

        import json
        from piltover.db.models import AuthCountry, AuthCountryCode

        with open(args.auth_countries_file) as f:
            countries = json.load(f)

        for country in countries:
            auth_country, _ = await AuthCountry.get_or_create(iso2=country["iso2"], defaults={
                "name": country["name"],
                "hidden": country["hidden"],
            })
            for code in country["codes"]:
                await AuthCountryCode.get_or_create(country=auth_country, code=code["code"], defaults={
                    "prefixes": code["prefixes"],
                    "patterns": code["patterns"],
                })

    reactions_dir = args.reactions_dir
    reactions_files_dir = reactions_dir / "files"
    if reactions and reactions_dir.exists() and reactions_files_dir.exists():
        from os import listdir
        import json

        from piltover.db.models import Reaction

        logger.info("Creating (or updating) reactions...")
        for reaction_file in listdir(reactions_dir):
            if not reaction_file.endswith(".json") or not reaction_file.split(".")[0].isdigit():
                continue

            try:
                reaction_index = int(reaction_file.split(".")[0])
            except ValueError:
                continue

            with open(reactions_dir / reaction_file) as f:
                reaction_info = json.load(f)

            defaults = {"title": reaction_info["title"], "reaction": reaction_info["reaction"]}

            for doc_name in (
                "static_icon", "appear_animation", "select_animation", "activate_animation", "effect_animation",
                "around_animation", "center_icon",
            ):
                if doc_name not in reaction_info:
                    continue
                defaults[doc_name] = await _upload_reaction_doc(reaction_index, reaction_info[doc_name])

            reaction, created = await Reaction.get_or_create(
                reaction_id=Reaction.reaction_to_uuid(reaction_info["reaction"]), defaults=defaults,
            )
            if created:
                logger.info(f"Created reaction \"{reaction.title}\" (\"{reaction.reaction}\" / \"{reaction_info['reaction']}\")")
            else:
                logger.info(f"Updating reaction \"{reaction.title}\" (\"{reaction.reaction}\" / \"{reaction_info['reaction']}\")")
                await reaction.update_from_dict(defaults).save()


async def migrate():
    migrations_dir = (args.data_dir / "migrations").absolute()

    command = Command({
        "connections": {"default": DB_CONNECTION_STRING},
        "apps": {"models": {"models": ["piltover.db.models", "aerich.models"], "default_connection": "default"}},
    }, location=str(migrations_dir))
    await command.init()
    if Path(migrations_dir).exists():
        await MigrateNoDowngrade.migrate("update", False)
        await command.upgrade(True)
    else:
        await command.init_db(True)

    await _create_system_data(args.create_system_user, args.create_auth_countries, args.create_reactions)
    await Tortoise.close_connections()


class PiltoverApp:
    def __init__(
            self, data_dir: Path, privkey: str | Path, pubkey: str | Path, host: str = "0.0.0.0", port: int = 4430,
            rabbitmq_address: str | None = None, redis_address: str | None = None,
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
        )

        if self._gateway.worker is not None:
            register_handlers(self._gateway.worker)

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

        logger.success(f"Running on {self._host}:{self._port}")
        await self._gateway.serve()

    @asynccontextmanager
    async def run_test(
            self, create_sys_user: bool = True, create_countries: bool = False, create_reactions: bool = False,
    ) -> AsyncIterator[Gateway]:
        await Tortoise.init(
            db_url="sqlite://:memory:",
            modules={"models": ["piltover.db.models"]},
            _create_db=True,
        )
        await Tortoise.generate_schemas()
        await _create_system_data(create_sys_user, create_countries, create_reactions)

        from piltover.app.handlers import testing
        if not testing.handler.registered:
            self._gateway.worker.register_handler(testing.handler)

        await self._gateway.broker.startup()
        server = await asyncio.start_server(self._gateway.accept_client, "127.0.0.1", 0)
        async with server:
            self._gateway.host, self._gateway.port = server.sockets[0].getsockname()
            yield self._gateway

        await self._gateway.broker.shutdown()
        await connections.close_all(True)
        await Cache.obj.clear()


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
)


if __name__ == "__main__":
    try:
        uvloop.install()
        asyncio.run(app.run())
    except KeyboardInterrupt:
        pass
