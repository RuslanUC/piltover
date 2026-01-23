from __future__ import annotations

import hashlib
import hmac
from time import time
from typing import cast, TYPE_CHECKING

from loguru import logger

from piltover.auth_data import AuthData
from piltover.cache import Cache
from piltover.db.models import UserAuthorization, AuthKey, ChatParticipant
from piltover.exceptions import Disconnection
from piltover.tl import TLObject, Updates, Long, Int
from piltover.tl.types.internal import ObjectWithLayerRequirement, TaggedLongVector

if TYPE_CHECKING:
    from piltover.gateway import Client


class Salt:
    __slots__ = ("salt", "valid_at",)

    def __init__(self, salt: bytes, valid_at: int) -> None:
        self.salt = salt
        self.valid_at = valid_at


# TODO: store sessions in redis or something (with non-acked messages) to be able to restore session after reconnect
class Session:
    __slots__ = (
        "client", "session_id", "auth_data", "min_msg_id", "user_id", "auth_id", "channel_ids", "auth_loaded_at",
        "channels_loaded_at", "salt_now", "salt_prev", "no_updates", "layer", "is_bot", "mfa_pending",
    )

    def __init__(self, session_id: int, client: Client | None = None, auth_data: AuthData | None = None) -> None:
        self.client = client
        self.session_id = session_id
        self.auth_data = auth_data

        self.min_msg_id = 0

        self.user_id: int | None = None
        self.auth_id: int | None = None
        self.is_bot = False
        self.mfa_pending = False
        self.auth_loaded_at = 0.

        self.channel_ids: list[int] = []
        self.channels_loaded_at = 0.

        self.salt_now = Salt(b"\x00" * 8, 0)
        self.salt_prev = Salt(b"\x00" * 8, 0)

        self.no_updates = False
        self.layer = 133

    def uniq_id(self) -> tuple[int, int]:
        key_id = 0 if self.auth_data is None else self.auth_data.auth_key_id
        return key_id, self.session_id

    def __hash__(self) -> int:
        return hash(self.uniq_id)

    # TODO: rewrite
    def set_client(self, client: Client) -> None:
        from piltover.session_manager import SessionManager

        # TODO: raise AuthKeyDuplicated if self.client is not None
        self.client = client
        SessionManager.broker.subscribe(self)

    # TODO: rewrite
    def destroy(self) -> None:
        from piltover.session_manager import SessionManager

        self.client = None
        SessionManager.broker.unsubscribe(self)
        SessionManager.cleanup(self)

    @staticmethod
    def _get_attr_or_element(obj: TLObject | list, field_name: str) -> TLObject | list:
        if isinstance(obj, list):
            return obj[int(field_name)]
        else:
            return getattr(obj, field_name)

    async def send(self, obj: TLObject) -> None:
        if self.client is None:
            return

        if isinstance(obj, ObjectWithLayerRequirement):
            field_paths = obj.fields
            obj = obj.object

            for field_path in field_paths:
                if field_path.min_layer <= self.layer <= field_path.max_layer:
                    continue

                field_path = field_path.field.split(".")
                parent = obj
                for field_name in field_path[:-1]:
                    parent = self._get_attr_or_element(parent, field_name)

                if not isinstance(parent, list):
                    continue

                del parent[int(field_path[-1])]

        if isinstance(obj, Updates) and self.auth_id is not None:
            if (auth := await UserAuthorization.get_or_none(id=self.auth_id)) is not None:
                auth.upd_seq += 1
                await auth.save(update_fields=["upd_seq"])
                obj.seq = auth.upd_seq
                obj.qts = auth.upd_qts

        try:
            await self.client.send(obj, self, False)
        except Disconnection:
            pass  # TODO: call self.client.on_disconnected() or something
        except Exception as e:
            logger.opt(exception=e).warning(f"Failed to send {obj} to {self.client}")

        if isinstance(obj, Updates):
            obj.seq = 0
            obj.qts = 0

    @staticmethod
    def make_salt(salt_key: bytes, auth_key_id: int, timestamp: int) -> bytes:
        return hmac.new(salt_key, Long.write(auth_key_id) + Int.write(timestamp), hashlib.sha1).digest()[:8]

    # TODO: store salt_key in session?
    def update_salts_maybe(self, salt_key: bytes, force: bool = False) -> None:
        if self.auth_data is None or self.auth_data.auth_key_id is None:
            self.salt_now = self.salt_prev = (b"\x00" * 8, 0)
            return

        now = int(time() // (30 * 60))
        if self.salt_now.valid_at == now and not force:
            return

        self.salt_now.salt = self.make_salt(salt_key, self.auth_data.auth_key_id, now)
        self.salt_now.valid_at = now

        self.salt_prev.salt = self.make_salt(salt_key, self.auth_data.auth_key_id, now - 1)
        self.salt_now.valid_at = now - 1

    async def fetch_layer(self) -> None:
        if self.auth_data.perm_auth_key_id is None:
            return

        perm_key_layer = cast(
            int | None,
            await AuthKey.get_or_none(id=self.auth_data.perm_auth_key_id).values_list("layer", flat=True),
        )
        if perm_key_layer is not None:
            self.layer = perm_key_layer

    def _reset_auth(self) -> None:
        from piltover.session_manager import SessionManager

        SessionManager.broker.unsubscribe_auth(self.auth_id, self)
        SessionManager.broker.unsubscribe_user(self.user_id, self)
        SessionManager.broker.channels_diff_update(self, self.channel_ids, [])

        self.user_id = None
        self.auth_id = None
        self.is_bot = False
        self.mfa_pending = False
        self.channel_ids.clear()

    async def refresh_auth_maybe(self, force_refresh_auth: bool = False) -> None:
        from piltover.session_manager import SessionManager

        if force_refresh_auth:
            self.auth_data = await AuthKey.get_auth_data(self.auth_data.auth_key_id)

        auth_key_id = self.auth_data.auth_key_id
        perm_auth_key_id = self.auth_data.perm_auth_key_id

        old_user_id = self.user_id
        old_auth_id = self.auth_id

        if auth_key_id is None or perm_auth_key_id is None:
            self._reset_auth()
            return

        if (time() - self.auth_loaded_at) > 60 or force_refresh_auth:
            logger.trace("Refreshing auth...")
            self.auth_loaded_at = time()

            auth = await UserAuthorization.get_or_none(key__id=perm_auth_key_id).select_related("user")
            if auth is not None:
                self.user_id = auth.user_id
                self.auth_id = auth.id
                self.is_bot = auth.user.bot
                self.mfa_pending = auth.mfa_pending
            else:
                self._reset_auth()
                return

        if self.auth_id is not None and not self.mfa_pending and (time() - self.channels_loaded_at) > 60 * 5:
            logger.trace("Refreshing channels...")
            self.channels_loaded_at = time()

            channel_ids: TaggedLongVector | None = await Cache.obj.get(f"channels:{self.user_id}")
            if channel_ids is None:
                channel_ids = TaggedLongVector(vec=[
                    channel_id
                    for channel_id in await ChatParticipant.filter(
                        channel_id__not_isnull=True, user__id=self.user_id, left=False,
                    ).values_list("channel_id", flat=True)
                ])
                await Cache.obj.set(f"channels:{self.user_id}", channel_ids, ttl=60 * 10)

            channel_ids: list[int] = channel_ids.vec
            old_channels = set(self.channel_ids)
            new_channels = set(channel_ids)
            channels_to_delete = old_channels - new_channels
            channels_to_add = new_channels - old_channels

            self.channel_ids = new_channels
            SessionManager.broker.channels_diff_update(self, channels_to_delete, channels_to_add)

        if old_user_id != self.user_id:
            if old_user_id:
                SessionManager.broker.unsubscribe_user(old_user_id, self)
            SessionManager.broker.subscribe_user(self.user_id, self)
        if old_auth_id != self.auth_id:
            if old_auth_id:
                SessionManager.broker.unsubscribe_auth(old_auth_id, self)
            SessionManager.broker.subscribe_auth(self.auth_id, self)
