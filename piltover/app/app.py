import argparse
import asyncio
from contextlib import asynccontextmanager
from os import getenv
from pathlib import Path
from types import SimpleNamespace

import uvloop
from aerich import Command, Migrate
from loguru import logger
from tortoise import Tortoise, connections

from piltover.app import help as help_, auth, updates, users, stories, account, messages, contacts, photos, \
    langpack, channels, upload, root_dir, internal
from piltover.gateway import Gateway
from piltover.utils import gen_keys, get_public_key_fingerprint, Keys

data = root_dir / "data"
data.mkdir(parents=True, exist_ok=True)

secrets = data / "secrets"
secrets.mkdir(parents=True, exist_ok=True)

DB_CONNECTION_STRING = getenv("DB_CONNECTION_STRING", "sqlite://data/secrets/piltover.db")


class MigrateNoDowngrade(Migrate):
    @classmethod
    def diff_models(cls, old_models: dict[str, dict], new_models: dict[str, dict], upgrade=True) -> None:
        if not upgrade:
            return

        return super(MigrateNoDowngrade, cls).diff_models(old_models, new_models, True)


async def _create_system_data(system_users: bool = True, countries_list: bool = True) -> None:
    if system_users:
        logger.info("Creating system user...")

        from piltover.db.models import User
        await User.update_or_create(id=777000, defaults={
            "phone_number": "42777",
            "first_name": "Piltover",
            "username": "piltover",
        })

    auth_countries_list_file = data / "auth_countries_list.json"
    if countries_list and auth_countries_list_file.exists():
        logger.info("Creating auth countries...")

        import json
        from piltover.db.models import AuthCountry, AuthCountryCode

        with open(auth_countries_list_file) as f:
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


async def migrate():
    migrations_dir = (data / "migrations").absolute()

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

    await _create_system_data(args.create_system_user, args.create_auth_countries)
    await Tortoise.close_connections()


class PiltoverApp:
    def __init__(
            self, privkey: str | Path, pubkey: str | Path, host: str = "0.0.0.0", port: int = 4430,
            rabbitmq_address: str | None = None, redis_address: str | None = None,
    ):
        self._host = host
        self._port = port

        privkey = privkey if isinstance(privkey, Path) else Path(privkey)
        pubkey = pubkey if isinstance(pubkey, Path) else Path(pubkey)
        if not (pubkey.exists() and privkey.exists()):
            with privkey.open("w+") as priv, pubkey.open("w+") as pub:
                keys = gen_keys()
                priv.write(keys.private_key)
                pub.write(keys.public_key)

        self._private_key = privkey.read_text()
        self._public_key = pubkey.read_text()

        self._gateway = Gateway(
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
            worker = self._gateway.worker
            worker.register_handler(help_.handler)
            worker.register_handler(auth.handler)
            worker.register_handler(updates.handler)
            worker.register_handler(users.handler)
            worker.register_handler(stories.handler)
            worker.register_handler(account.handler)
            worker.register_handler(messages.handler)
            worker.register_handler(photos.handler)
            worker.register_handler(contacts.handler)
            worker.register_handler(langpack.handler)
            worker.register_handler(channels.handler)
            worker.register_handler(upload.handler)
            worker.register_handler(internal.handler)

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
    async def run_test(self) -> int:
        await Tortoise.init(
            db_url="sqlite://:memory:",
            modules={"models": ["piltover.db.models"]},
            _create_db=True,
        )
        await Tortoise.generate_schemas()
        await _create_system_data()

        from piltover.app import testing
        try:
            self._gateway.worker.register_handler(testing.handler)
        except RuntimeError:
            ...

        await self._gateway.broker.startup()
        server = await asyncio.start_server(self._gateway.accept_client, "127.0.0.1", 0)
        async with server:
            self._gateway.host, self._gateway.port = server.sockets[0].getsockname()
            yield self._gateway

        await self._gateway.broker.shutdown()
        await connections.close_all(True)


# TODO: add host and port to arguments
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--create-system-user", action="store_true", help="Create system user with id 777000")
    parser.add_argument("--create-auth-countries", action="store_true", help="Insert auth countries to database")
    parser.add_argument("--privkey-file", type=Path,
                        help="Path to private key file (will be created if does not exist)",
                        default=secrets / "privkey.asc")
    parser.add_argument("--pubkey-file", type=Path,
                        help="Path to public key file (will be created if does not exist)",
                        default=secrets / "pubkey.asc")
    parser.add_argument("--rabbitmq-address", type=str, required=False,
                        help="Address of rabbitmq server in \"amqp://user:password@host:port\" format",
                        default=None)
    parser.add_argument("--redis-address", type=str, required=False,
                        help="Address of redis server in \"redis://host:port\" format",
                        default=None)
    args = parser.parse_args()
else:
    args = SimpleNamespace(
        create_system_user=True,
        create_auth_countries=True,
        privkey_file=secrets / "privkey.asc",
        pubkey_file=secrets / "pubkey.asc",
        rabbitmq_address=None,
        redis_address=None,
    )


app = PiltoverApp(
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
