import asyncio
from os import getenv
from pathlib import Path

import uvloop
from loguru import logger

from piltover.app import system, help as help_, auth, updates, users, stories, account, messages, contacts, photos, \
    langpack
from piltover.server import Server
from piltover.types import Keys
from piltover.utils import gen_keys, get_public_key_fingerprint

root = Path(__file__).parent.parent.resolve(strict=True)
data = root / "data"
data.mkdir(parents=True, exist_ok=True)

secrets = data / "secrets"
secrets.mkdir(parents=True, exist_ok=True)

privkey = secrets / "privkey.asc"
pubkey = secrets / "pubkey.asc"

if not getenv("DISABLE_HR"):
    # Hot code reloading
    import jurigged


    def log(s: jurigged.live.WatchOperation):
        if hasattr(s, "filename") and "unknown" not in s.filename:
            file = Path(s.filename)
            print("Reloaded", file.relative_to(root))


    jurigged.watch("piltover/*.py", logger=log)


async def main():
    if not (pubkey.exists() and privkey.exists()):
        with privkey.open("w+") as priv, pubkey.open("w+") as pub:
            keys: Keys = gen_keys()
            priv.write(keys.private_key)
            pub.write(keys.public_key)

    private_key = privkey.read_text()
    public_key = pubkey.read_text()

    fp = get_public_key_fingerprint(public_key, signed=True)
    logger.info(
        "Pubkey fingerprint: {fp:x} ({no_sign})",
        fp=fp,
        no_sign=fp.to_bytes(8, "big", signed=True).hex(),
    )

    pilt = Server(
        server_keys=Keys(
            private_key=private_key,
            public_key=public_key,
        )
    )

    pilt.register_handler(system.handler)
    pilt.register_handler(help_.handler)
    pilt.register_handler(auth.handler)
    pilt.register_handler(updates.handler)
    pilt.register_handler(users.handler)
    pilt.register_handler(stories.handler)
    pilt.register_handler(account.handler)
    pilt.register_handler(messages.handler)
    pilt.register_handler(photos.handler)
    pilt.register_handler(contacts.handler)
    pilt.register_handler(langpack.handler)

    logger.success("Running on {host}:{port}", host=pilt.HOST, port=pilt.PORT)
    await pilt.serve()


if __name__ == "__main__":
    try:
        uvloop.install()
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
