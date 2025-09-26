import argparse
from os import getenv
from pathlib import Path
from types import SimpleNamespace
from typing import Literal

from taskiq import TaskiqEvents, AsyncBroker
from tortoise import Tortoise

from piltover.app.handlers import register_handlers
from piltover.cache import Cache
from piltover.utils import gen_keys, Keys
from piltover.worker import Worker

DB_CONNECTION_STRING = getenv("DB_CONNECTION_STRING", "sqlite://data/secrets/piltover.db")


class ArgsNamespace(SimpleNamespace):
    data_dir: Path
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


class PiltoverWorker:
    def __init__(
            self, data_dir: Path, privkey: str | Path, pubkey: str | Path, rabbitmq_address: str | None = None,
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
            data_dir=data_dir,
            server_keys=Keys(
                private_key=self._private_key,
                public_key=self._public_key,
            ),
            rabbitmq_address=rabbitmq_address,
            redis_address = redis_address,
        )

        register_handlers(self._worker)

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
    parser.add_argument("--data-dir", type=Path,
                        help="Path to data directory, where all files, server keys and other server data are stored.",
                        default=Path("./data"))
    parser.add_argument("--privkey-file", type=Path, default=None,
                        help=(
                            "Path to private key file. "
                            "By default, <data-dir>/secrets/privkey.asc will be used."
                            "Will be created if does not exist."
                        ))
    parser.add_argument("--pubkey-file", type=Path, default=None,
                        help=(
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
    args = parser.parse_args(namespace=ArgsNamespace())
    args.fill_defaults()
else:
    args = ArgsNamespace(
        data_dir=Path("./data") / "testing",
        privkey_file=None,
        pubkey_file=None,
        rabbitmq_address=None,
        redis_address=None,
        cache_backend="memory",
        cache_endpoint=None,
        cache_port=None,
    )


Cache.init(args.cache_backend, endpoint=args.cache_endpoint, port=args.cache_port)
worker = PiltoverWorker(args.data_dir, args.privkey_file, args.pubkey_file, args.rabbitmq_address, args.redis_address)
broker = worker.get_broker()
