from __future__ import annotations

from typing import TYPE_CHECKING

from piltover.auth_data import AuthData
from piltover.context import NeedContextValuesContext
from piltover.session import Session
from piltover.tl import TLObject, Vector
from piltover.tl.types.internal import MessageToUsersShort, ChannelSubscribe, MessageToUsers, ObjectWithLayerRequirement

if TYPE_CHECKING:
    from piltover.gateway import Client
    from piltover.message_brokers.base_broker import BaseMessageBroker


class SessionManager:
    sessions: dict[tuple[int, int], Session] = {}
    broker: BaseMessageBroker | None = None

    @classmethod
    def set_broker(cls, broker: BaseMessageBroker) -> None:
        cls.broker = broker

    @classmethod
    def get_or_create(cls, session_id: int, client: Client, auth_data: AuthData) -> tuple[Session, bool]:
        uniq_id = auth_data.auth_key_id, session_id

        if uniq_id in cls.sessions:
            return cls.sessions[uniq_id], False

        cls.sessions[uniq_id] = session = Session(client=client, session_id=session_id, auth_data=auth_data)
        return session, True

    @classmethod
    def cleanup(cls, session: Session) -> None:
        uniq_id = session.auth_data.auth_key_id, session.session_id
        if uniq_id in cls.sessions:
            del cls.sessions[uniq_id]

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
