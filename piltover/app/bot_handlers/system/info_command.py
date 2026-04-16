import asyncio
import platform
import string
import sys
from types import NoneType
from typing import Any

from loguru import logger

from piltover.app.bot_handlers.interaction_handler import BotInteractionHandler
from piltover.app.utils.formatable_text_with_entities import FormatableTextWithEntities
from piltover.config import SYSTEM_CONFIG, APP_CONFIG
from piltover.context import request_ctx
from piltover.db.models import Peer, MessageRef
from piltover.tl import Long

_text = FormatableTextWithEntities("""
Instance name: **{instance_name}**
Git revision: `{git_commit}`
Python version: `{python_version}`
Platform: `{platform_name}`
Storage backend: `{storage_backend}`
Cache backend: `{cache_backend}`
Tracing enabled: `{tracing_enabled}`
Gifs enabled: `{gifs_enabled}`
Server key fingerprint (signed): `{pubkey_fp_signed}`
Server key fingerprint (unsigned): `{pubkey_fp_unsigned}`
""".strip())


async def send_bot_message(peer: Peer, text: str, entities: list[dict[str, str | int]] | None = None) -> MessageRef:
    messages = await MessageRef.create_for_peer(peer, peer.user, opposite=False, message=text, entities=entities)
    return messages[peer]


class Info(BotInteractionHandler[NoneType, NoneType]):
    __slots__ = ("_cached_text", "_cached_entities", "_lock",)

    def __init__(self) -> None:
        super().__init__(None)
        if SYSTEM_CONFIG.enable_system_bot:
            self.command("info").do(self._handler).register()

        self._cached_text: str | None = None
        self._cached_entities: list[dict[str, Any]] | None = None
        self._lock = asyncio.Lock()

    async def _get_info(self) -> None:
        if self._cached_text is not None:
            return

        proc = await asyncio.create_subprocess_exec(
            "git", "rev-parse", "HEAD",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=1.5)
        except TimeoutError as e:
            logger.opt(exception=e).warning("Failed to get git revision due to timeout")
            git_commit = "\"git rev-parse\" timed out"
        except Exception as e:
            logger.opt(exception=e).warning("Failed to get git revision due to exception")
            git_commit = "\"git rev-parse\" timed out"
        else:
            git_commit = stdout.partition(b"\n")[0].strip().decode("utf8")
            if len(git_commit) != 40 or not all(c in string.hexdigits for c in git_commit):
                logger.warning(f"\"git rev-parse\" returned invalid data: {git_commit}")
                git_commit = "\"git rev-parse\" returned invalid data"
            else:
                git_commit = git_commit

        if proc.returncode is None:
            try:
                proc.kill()
            except Exception as e:
                logger.opt(exception=e).warning("Failed to kill \"git rev-parse\" process")

        pubkey_fp_unsigned = request_ctx.get().worker.fingerprint
        pubkey_fp_signed = Long.read_bytes(Long.write(pubkey_fp_unsigned, signed=False), signed=True)

        self._cached_text, self._cached_entities = _text.format(
            instance_name=APP_CONFIG.name,
            git_commit=git_commit,
            python_version=sys.version,
            platform_name=platform.platform(),
            storage_backend="local",
            cache_backend=SYSTEM_CONFIG.cache.backend,
            tracing_enabled=SYSTEM_CONFIG.debug_tracing.backend != "noop",
            gifs_enabled=APP_CONFIG.gifs is not None,
            pubkey_fp_signed=hex(pubkey_fp_signed),
            pubkey_fp_unsigned=hex(pubkey_fp_unsigned),
        )

    async def _handler(self, peer: Peer, _1: MessageRef, _2: None) -> MessageRef:
        async with self._lock:
            await self._get_info()

        return await send_bot_message(peer, self._cached_text, self._cached_entities)