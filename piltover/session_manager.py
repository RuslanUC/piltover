from __future__ import annotations

from dataclasses import dataclass, field
from time import time
from typing import TYPE_CHECKING

from loguru import logger

from piltover.context import NeedContextValuesContext
from piltover.db.models import UserAuthorization
from piltover.exceptions import Disconnection
from piltover.layer_converter.manager import LayerConverter
from piltover.tl import TLObject, Updates, Vector
from piltover.tl.core_types import Message, MsgContainer
from piltover.tl.types.internal import MessageToUsersShort, ChannelSubscribe, MessageToUsers, ObjectWithLayerRequirement
from piltover.tl.utils import is_content_related

if TYPE_CHECKING:
    from piltover.gateway import Client
    from piltover.message_brokers.base_broker import BaseMessageBroker


@dataclass(slots=True)
class KeyInfo:
    auth_key: bytes
    auth_key_id: int
    perm_auth_key_id: int


class MsgIdValues:
    __slots__ = ("last_time", "offset",)

    def __init__(self, last_time: int = 0, offset: int = 0) -> None:
        self.last_time = last_time
        self.offset = offset


@dataclass
class Session:
    # TODO: store sessions in redis or something (with non-acked messages) to be able to restore session after reconnect

    client: Client | None
    session_id: int
    msg_id_values: MsgIdValues
    auth_key: KeyInfo | None = None
    user_id: int | None = None
    channel_ids: list[int] = field(default_factory=list)
    min_msg_id: int = 0
    online: bool = False
    auth_id: int | None = None
    need_auth_refresh: bool = False

    outgoing_content_related_msgs = 0

    def msg_id(self, in_reply: bool) -> int:
        # Client message identifiers are divisible by 4, server message
        # identifiers modulo 4 yield 1 if the message is a response to
        # a client message, and 3 otherwise.

        now = int(time())
        self.msg_id_values.offset = (self.msg_id_values.offset + 4) if now == self.msg_id_values.last_time else 0
        self.msg_id_values.last_time = now
        msg_id = (now * 2 ** 32) + self.msg_id_values.offset + (1 if in_reply else 3)

        assert msg_id % 4 in [1, 3], f"Invalid server msg_id: {msg_id}"
        return msg_id

    def get_outgoing_seq_no(self, obj: TLObject) -> int:
        ret = self.outgoing_content_related_msgs * 2
        if is_content_related(obj):
            self.outgoing_content_related_msgs += 1
            ret += 1
        return ret

    # https://core.telegram.org/mtproto/description#message-identifier-msg-id
    def pack_message(self, obj: TLObject, in_reply: bool) -> Message:
        try:
            downgraded_maybe = LayerConverter.downgrade(obj, self.client.layer)
        except Exception as e:
            logger.opt(exception=e).error("Failed to downgrade object")
            raise

        return Message(
            message_id=self.msg_id(in_reply=in_reply),
            seq_no=self.get_outgoing_seq_no(obj),
            obj=downgraded_maybe,
        )

    # https://core.telegram.org/mtproto/description#message-identifier-msg-id
    def pack_container(self, objects: list[tuple[TLObject, bool]]) -> Message:
        container = MsgContainer(messages=[
            Message(
                message_id=self.msg_id(in_reply=in_reply),
                seq_no=self.get_outgoing_seq_no(obj),
                obj=obj,
            )
            for obj, in_reply in objects
        ])

        return self.pack_message(container, False)

    def __hash__(self) -> int:
        return self.session_id

    def set_user_id(self, user_id: int, need_auth_refresh: bool = False) -> None:
        self.user_id = user_id
        self.online = True
        if need_auth_refresh:
            self.need_auth_refresh = True

        SessionManager.broker.subscribe(self)

    def destroy(self) -> None:
        self.online = False
        SessionManager.broker.unsubscribe(self)
        SessionManager.cleanup(self)

    @staticmethod
    def _get_attr_or_element(obj: TLObject | list, field_name: str) -> TLObject | list:
        if isinstance(obj, list):
            return obj[int(field_name)]
        else:
            return getattr(obj, field_name)

    @staticmethod
    def _set_attr_or_element(obj: TLObject | list, field_name: str, value: TLObject) -> None:
        if isinstance(obj, list):
            obj[int(field_name)] = value
        else:
            setattr(obj, field_name, value)

    async def send(self, obj: TLObject) -> None:
        if not self.online:
            return

        if isinstance(obj, ObjectWithLayerRequirement):
            field_paths = obj.fields
            obj = obj.object

            for field_path in field_paths:
                if field_path.min_layer <= self.client.layer <= field_path.max_layer:
                    continue

                field_path = field_path.field.split(".")
                parent = obj
                for field_name in field_path[:-1]:
                    parent = self._get_attr_or_element(parent, field_name)

                if not isinstance(parent, list):
                    continue

                del parent[int(field_path[-1])]

        if isinstance(obj, Updates) and self.auth_key is not None and self.auth_key.perm_auth_key_id:
            # TODO: replace with id=self.auth_id ??
            if (auth := await UserAuthorization.get_or_none(key__id=self.auth_key.perm_auth_key_id)) is not None:
                auth.upd_seq += 1
                await auth.save(update_fields=["upd_seq"])
                obj.seq = auth.upd_seq
                obj.qts = auth.upd_qts

        try:
            await self.client.send(obj, self, False, need_auth_refresh=self.need_auth_refresh)
            self.need_auth_refresh = False
        except Disconnection:
            if self.auth_key is not None:
                self.destroy()
        except Exception as e:
            logger.opt(exception=e).warning(f"Failed to send {obj} to {self.client}")

        if isinstance(obj, Updates):
            obj.seq = 0
            obj.qts = 0


class SessionManager:
    sessions: dict[int, dict[int, Session]] = {}
    broker: BaseMessageBroker | None = None

    @classmethod
    def set_broker(cls, broker: BaseMessageBroker) -> None:
        cls.broker = broker

    @classmethod
    def get_or_create(
            cls, client: Client, session_id: int, msg_id_values: MsgIdValues | None = None,
    ) -> tuple[Session, bool]:
        if session_id not in cls.sessions:
            cls.sessions[session_id] = {}
        if client.auth_data.auth_key_id in cls.sessions[session_id]:
            return cls.sessions[session_id][client.auth_data.auth_key_id], False

        if msg_id_values is None:
            msg_id_values = MsgIdValues()

        session = Session(
            client=client,
            session_id=session_id,
            auth_key=KeyInfo(
                auth_key=client.auth_data.auth_key,
                auth_key_id=client.auth_data.auth_key_id,
                perm_auth_key_id=client.auth_data.perm_auth_key_id,
            ),
            msg_id_values=msg_id_values,
        )
        cls.sessions[session_id][client.auth_data.auth_key_id] = session
        return session, True

    @classmethod
    def cleanup(cls, session: Session) -> None:
        key_id = session.auth_key.auth_key_id
        if session.session_id in cls.sessions and key_id in cls.sessions[session.session_id]:
            del cls.sessions[session.session_id][key_id]

    @classmethod
    async def send(
            cls, obj: TLObject | Vector, user_id: int | list[int] | None = None, key_id: int | list[int] | None = None,
            channel_id: int | list[int] | None = None, auth_id: int | list[int] | None = None,
            ignore_auth_id: int | list[int] | None = None, min_layer: int | None = None,
    ) -> None:
        if not user_id and not key_id and not channel_id and not auth_id:
            return

        if isinstance(user_id, list) and len(user_id) == 1:
            user_id = user_id[0]
        if isinstance(key_id, list) and len(key_id) == 1:
            key_id = key_id[0]
        if isinstance(channel_id, list) and len(channel_id) == 1:
            channel_id = channel_id[0]
        if isinstance(auth_id, list) and len(auth_id) == 1:
            auth_id = auth_id[0]
        if isinstance(ignore_auth_id, list) and len(ignore_auth_id) == 1:
            ignore_auth_id = ignore_auth_id[0]

        is_short = (
                (user_id is None or isinstance(user_id, int))
                and (key_id is None or isinstance(key_id, int))
                and (channel_id is None or isinstance(channel_id, int))
                and (auth_id is None or isinstance(auth_id, int))
                and (ignore_auth_id is None or isinstance(ignore_auth_id, int))
        )

        ctx = NeedContextValuesContext()
        obj.check_for_ctx_values(ctx)

        if ctx.any():
            if isinstance(obj, ObjectWithLayerRequirement):
                obj.object = ctx.to_tl(obj.object)
                # TODO: this is (probably) a temporary fix (?)
                for field_ in obj.fields:
                    field_.field = f"obj.{field_.field}"
            else:
                obj = ctx.to_tl(obj)

        if is_short:
            message = MessageToUsersShort(
                user=user_id,
                key_id=key_id,
                channel_id=channel_id,
                auth_id=auth_id,
                ignore_auth_id=ignore_auth_id,
                obj=obj,
                min_layer=min_layer,
            )
        else:
            message = MessageToUsers(
                users=[user_id] if isinstance(user_id, int) else user_id,
                key_ids=[key_id] if isinstance(key_id, int) else key_id,
                channel_ids=[channel_id] if isinstance(channel_id, int) else channel_id,
                auth_ids=[auth_id] if isinstance(auth_id, int) else auth_id,
                ignore_auth_id=[ignore_auth_id] if isinstance(ignore_auth_id, int) else ignore_auth_id,
                obj=obj,
                min_layer=min_layer,
            )

        await cls.broker.send(message)

    @classmethod
    async def subscribe_to_channel(cls, channel_id: int, user_ids: list[int]) -> None:
        if user_ids and channel_id:
            await cls.broker.send(ChannelSubscribe(channel_ids=[channel_id], user_ids=user_ids, subscribe=True))

    @classmethod
    async def unsubscribe_from_channel(cls, channel_id: int, user_ids: list[int]) -> None:
        if user_ids and channel_id:
            await cls.broker.send(ChannelSubscribe(channel_ids=[channel_id], user_ids=user_ids, subscribe=False))
