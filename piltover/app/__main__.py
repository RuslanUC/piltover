import asyncio
from contextlib import asynccontextmanager
from os import getenv
from pathlib import Path
from time import time

import uvloop
from aerich import Command, Migrate
from loguru import logger
from tortoise import Tortoise, connections

from piltover.app import system, help as help_, auth, updates, users, stories, account, messages, contacts, photos, \
    langpack, channels, upload, root_dir
from piltover.db.models import AuthKey, User
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


async def _create_system_data() -> None:
    await User.update_or_create(id=777000, defaults={
        "phone_number": "42777",
        "first_name": "Piltover",
        "username": "piltover",
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

    await _create_system_data()
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

    async def run(self, host: str | None = None, port: int | None = None, *, reload: bool = False):
        self._host = host or self._host
        self._port = port or self._port

        fp = get_public_key_fingerprint(self._public_key, signed=True)
        logger.info(
            "Pubkey fingerprint: {fp:x} ({no_sign})",
            fp=fp,
            no_sign=fp.to_bytes(8, "big", signed=True).hex(),
        )

        if reload:
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


app = PiltoverApp(secrets / "privkey.asc", secrets / "pubkey.asc")


if __name__ == "__main__":
    try:
        uvloop.install()
        asyncio.run(app.run(reload=True))
    except KeyboardInterrupt:
        pass
