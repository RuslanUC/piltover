import argparse
from os import getenv
from pathlib import Path
from types import SimpleNamespace

from taskiq import TaskiqEvents, AsyncBroker
from tortoise import Tortoise

from piltover.app import root_dir
from piltover.app.handlers import help as help_, auth, updates, users, stories, account, messages, contacts, photos, \
    langpack, channels, upload, internal
from piltover.utils import gen_keys, Keys
from piltover.worker import Worker

data = root_dir / "data"
data.mkdir(parents=True, exist_ok=True)

secrets = data / "secrets"
secrets.mkdir(parents=True, exist_ok=True)

DB_CONNECTION_STRING = getenv("DB_CONNECTION_STRING", "sqlite://data/secrets/piltover.db")


class PiltoverWorker:
    def __init__(
            self, privkey: str | Path, pubkey: str | Path, rabbitmq_address: str | None = None,
            redis_address: str | None = None
    ):
        privkey = privkey if isinstance(privkey, Path) else Path(privkey)
        pubkey = pubkey if isinstance(pubkey, Path) else Path(pubkey)
        if not (pubkey.exists() and privkey.exists()):
            with privkey.open("w+") as priv, pubkey.open("w+") as pub:
                keys = gen_keys()
                priv.write(keys.private_key)
                pub.write(keys.public_key)

        self._private_key = privkey.read_text()
        self._public_key = pubkey.read_text()

        self._worker = Worker(
            server_keys=Keys(
                private_key=self._private_key,
                public_key=self._public_key,
            ),
            rabbitmq_address=rabbitmq_address,
            redis_address = redis_address,
        )

        self._worker.register_handler(help_.handler)
        self._worker.register_handler(auth.handler)
        self._worker.register_handler(updates.handler)
        self._worker.register_handler(users.handler)
        self._worker.register_handler(stories.handler)
        self._worker.register_handler(account.handler)
        self._worker.register_handler(messages.handler)
        self._worker.register_handler(photos.handler)
        self._worker.register_handler(contacts.handler)
        self._worker.register_handler(langpack.handler)
        self._worker.register_handler(channels.handler)
        self._worker.register_handler(upload.handler)
        self._worker.register_handler(internal.handler)

        self._worker.broker.add_event_handler(TaskiqEvents.WORKER_STARTUP, self._run)

    @staticmethod
    async def _run():
        await Tortoise.init(
            db_url=DB_CONNECTION_STRING,
            modules={"models": ["piltover.db.models"]},
        )

    def get_broker(self) -> AsyncBroker:
        return self._worker.broker


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
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
        privkey_file=secrets / "privkey.asc",
        pubkey_file=secrets / "pubkey.asc",
        rabbitmq_address=None,
        redis_address=None,
    )


worker = PiltoverWorker(args.privkey_file, args.pubkey_file, args.rabbitmq_address, args.redis_address)
broker = worker.get_broker()
