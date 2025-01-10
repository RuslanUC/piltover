import argparse
import asyncio
from contextlib import asynccontextmanager
from os import getenv
from pathlib import Path
from time import time
from types import SimpleNamespace

import uvloop
from aerich import Command, Migrate
from loguru import logger
from tortoise import Tortoise, connections

from piltover.app import system, help as help_, auth, updates, users, stories, account, messages, contacts, photos, \
    langpack, channels, upload, root_dir, internal
from piltover.db.models import AuthKey
from piltover.db.models.authkey import TempAuthKey
from piltover.high_level import Server
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
    def __init__(self, privkey: str | Path, pubkey: str | Path, host: str = "0.0.0.0", port: int=4430):
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

        self._server = Server(
            host=host,
            port=port,
            server_keys=Keys(
                private_key=self._private_key,
                public_key=self._public_key,
            )
        )

        self._server.register_handler_low(system.handler)
        self._server.register_handler(help_.handler)
        self._server.register_handler(auth.handler)
        self._server.register_handler(updates.handler)
        self._server.register_handler(users.handler)
        self._server.register_handler(stories.handler)
        self._server.register_handler(account.handler)
        self._server.register_handler(messages.handler)
        self._server.register_handler(photos.handler)
        self._server.register_handler(contacts.handler)
        self._server.register_handler(langpack.handler)
        self._server.register_handler(channels.handler)
        self._server.register_handler(upload.handler)
        self._server.register_handler(internal.handler)

        self._server.on_auth_key_set(self._auth_key_set)
        self._server.on_auth_key_get(self._auth_key_get)

    @staticmethod
    async def _auth_key_set(auth_key_id: int, auth_key_bytes: bytes, expires_in: int | None) -> None:
        if expires_in:
            await TempAuthKey.create(id=str(auth_key_id), auth_key=auth_key_bytes, expires_at=int(time() + expires_in))
        else:
            await AuthKey.create(id=str(auth_key_id), auth_key=auth_key_bytes)
        logger.debug(f"Set auth key: {auth_key_id}")

    @staticmethod
    async def _auth_key_get(auth_key_id: int) -> tuple[int, bytes, bool] | None:
        logger.debug(f"Requested auth key: {auth_key_id}")
        if key := await AuthKey.get_or_temp(auth_key_id):
            return auth_key_id, key.auth_key, isinstance(key, TempAuthKey)

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

        logger.success("Running on {host}:{port}", host=self._host, port=self._port)
        await self._server.serve()

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
            self._server.register_handler(testing.handler)
        except RuntimeError:
            ...

        server = await asyncio.start_server(self._server.accept_client, "127.0.0.1", 0)
        async with server:
            self._server.host, self._server.port = server.sockets[0].getsockname()
            yield self._server

        await connections.close_all(True)


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
    args = parser.parse_args()
else:
    args = SimpleNamespace(
        create_system_user=True,
        create_auth_countries=True,
        privkey_file=secrets / "privkey.asc",
        pubkey_file=secrets / "pubkey.asc",
    )


app = PiltoverApp(args.privkey_file, args.pubkey_file)


if __name__ == "__main__":
    try:
        uvloop.install()
        asyncio.run(app.run())
    except KeyboardInterrupt:
        pass
