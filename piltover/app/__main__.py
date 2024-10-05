import asyncio
from os import getenv
from pathlib import Path
from time import time

import uvloop
from aerich import Command
from loguru import logger
from tortoise import Tortoise

from piltover.app import system, help as help_, auth, updates, users, stories, account, messages, contacts, photos, \
    langpack, channels, upload, root_dir
from piltover.db.models import AuthKey
from piltover.db.models.authkey import TempAuthKey
from piltover.high_level import Server
from piltover.types import Keys
from piltover.utils import gen_keys, get_public_key_fingerprint

data = root_dir / "data"
data.mkdir(parents=True, exist_ok=True)

secrets = data / "secrets"
secrets.mkdir(parents=True, exist_ok=True)

DB_CONNECTION_STRING = getenv("DB_CONNECTION_STRING", "sqlite://data/secrets/piltover.db")


async def migrate():
    migrations_dir = (data / "migrations").absolute()

    command = Command({
        "connections": {"default": DB_CONNECTION_STRING},
        "apps": {"models": {"models": ["piltover.db.models", "aerich.models"], "default_connection": "default"}},
    }, location=str(migrations_dir))
    await command.init()
    if Path(migrations_dir).exists():
        await command.migrate()
        await command.upgrade(True)
    else:
        await command.init_db(True)
    await Tortoise.close_connections()


class PiltoverApp:
    def __init__(self, privkey: str | Path, pubkey: str | Path, host: str = "0.0.0.0", port: int=4430):
        self._host = host
        self._port = port

        privkey = privkey if isinstance(privkey, Path) else Path(privkey)
        pubkey = pubkey if isinstance(pubkey, Path) else Path(pubkey)
        if not (pubkey.exists() and privkey.exists()):
            with privkey.open("w+") as priv, pubkey.open("w+") as pub:
                keys: Keys = gen_keys()
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
    async def _auth_key_set(auth_key_id: int, auth_key_bytes: bytes) -> None:
        await AuthKey.create(id=str(auth_key_id), auth_key=auth_key_bytes)
        logger.debug(f"Set auth key: {auth_key_id}")

    @staticmethod
    async def _auth_key_get(auth_key_id: int, temp: bool = False) -> tuple[int, bytes] | None:
        logger.debug(f"Requested auth key: {auth_key_id}")
        if temp:
            auth_key = await TempAuthKey.get_or_none(id=str(auth_key_id), expires__gt=int(time())) \
                .select_related("perm_key")
            if auth_key is None:
                return
            return auth_key_id, auth_key.auth_key
        if (auth_key := await AuthKey.get_or_none(id=str(auth_key_id))) is not None:
            return auth_key_id, auth_key.auth_key

    @staticmethod
    def _setup_reload():
        if getenv("DISABLE_HR"):
            return

        import jurigged

        def log(s: jurigged.live.WatchOperation):
            if hasattr(s, "filename") and "unknown" not in s.filename:
                file = Path(s.filename)
                print("Reloaded", file.relative_to(root_dir))

        jurigged.watch("piltover/[!tl]*.py", logger=log)

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
            self._setup_reload()
            await migrate()

        await Tortoise.init(
            db_url=DB_CONNECTION_STRING,
            modules={"models": ["piltover.db.models"]},
        )

        logger.success("Running on {host}:{port}", host=self._host, port=self._port)
        await self._server.serve()


app = PiltoverApp(secrets / "privkey.asc", secrets / "pubkey.asc")


if __name__ == "__main__":
    try:
        uvloop.install()
        asyncio.run(app.run(reload=True))
    except KeyboardInterrupt:
        pass
