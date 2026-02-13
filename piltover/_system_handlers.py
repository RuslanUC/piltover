from __future__ import annotations

from asyncio import get_running_loop
from datetime import datetime, UTC
from time import time
from typing import TYPE_CHECKING, Awaitable, Callable

from loguru import logger

from piltover.db.models import UserAuthorization, AuthKey
from piltover.tl import InitConnection, MsgsAck, Ping, Pong, PingDelayDisconnect, InvokeWithLayer, InvokeAfterMsg, \
    InvokeWithoutUpdates, RpcDropAnswer, DestroySession, DestroySessionOk, RpcAnswerUnknown, GetFutureSalts, \
    FutureSalt, Long
from piltover.tl.core_types import Message, RpcResult, FutureSalts

if TYPE_CHECKING:
    from piltover.gateway import Client
    from piltover.session import Session


async def msgs_ack(_1: Client, _2: Message[MsgsAck], _3: Session) -> None:
    return


async def ping(_1: Client, request: Message[Ping], _2: Session) -> Pong:
    return Pong(msg_id=request.message_id, ping_id=request.obj.ping_id)


async def ping_delay_disconnect(client: Client, request: Message[PingDelayDisconnect], _: Session) -> Pong:
    if client.disconnect_timeout is not None and request.obj.disconnect_delay > 0:
        client.disconnect_timeout.reschedule(get_running_loop().time() + request.obj.disconnect_delay)

    return Pong(msg_id=request.message_id, ping_id=request.obj.ping_id)


async def _invoke_inner_query(client: Client, request: Message, session: Session) -> RpcResult:
    return await client.propagate(
        Message(
            obj=request.obj.query,
            message_id=request.message_id,
            seq_no=request.seq_no,
        ),
        session,
    )


async def invoke_with_layer(client: Client, request: Message[InvokeWithLayer], session: Session) -> RpcResult:
    if request.obj.layer > session.layer:
        logger.trace(f"saving layer for key {session.auth_data.perm_auth_key_id}")
        await AuthKey.filter(id=session.auth_data.perm_auth_key_id).update(layer=request.obj.layer)
    session.layer = request.obj.layer
    return await _invoke_inner_query(client, request, session)


async def invoke_after_msg(client: Client, request: Message[InvokeAfterMsg], session: Session) -> RpcResult:
    return await _invoke_inner_query(client, request, session)


async def invoke_without_updates(client: Client, request: Message[InvokeWithoutUpdates], session: Session) -> RpcResult:
    session.no_updates = True
    return await _invoke_inner_query(client, request, session)


async def init_connection(client: Client, request: Message[InitConnection], session: Session) -> RpcResult:
    # hmm yes yes, I trust you client
    # the api id is always correct, it has always been!
    authorization = await UserAuthorization.get_or_none(key__id=session.auth_data.perm_auth_key_id)
    if authorization is not None:
        # TODO: set api id
        authorization.active_at = datetime.now(UTC)
        authorization.device_model = request.obj.device_model
        authorization.system_version = request.obj.system_version
        authorization.app_version = request.obj.app_version
        authorization.ip = client.peername[0]

        await authorization.save(update_fields=["active_at", "device_model", "system_version", "app_version", "ip"])

        if not session.no_updates:
            ...  # TODO: subscribe user to updates manually

    logger.info(f"initConnection with Api ID: {request.obj.api_id}")

    return await _invoke_inner_query(client, request, session)


async def destroy_session(_1: Client, request: Message[DestroySession], _3: Session) -> DestroySessionOk:
    return DestroySessionOk(session_id=request.obj.session_id)


async def rpc_drop_answer(_1: Client, request: Message[RpcDropAnswer], _3: Session) -> RpcResult:
    return RpcResult(req_msg_id=request.message_id, result=RpcAnswerUnknown())


async def get_future_salts(client: Client, request: Message[GetFutureSalts], session: Session) -> FutureSalts:
    limit = max(min(request.obj.num, 1), 64)
    base_timestamp = int(time() // (30 * 60))

    return FutureSalts(
        req_msg_id=request.message_id,
        now=int(time()),
        salts=[
            FutureSalt(
                valid_since=(base_timestamp + salt_offset) * 30 * 60,
                valid_until=(base_timestamp + salt_offset + 1) * 30 * 60,
                salt=Long.read_bytes(session.make_salt(
                    client.server.salt_key, session.auth_data.auth_key_id, base_timestamp + salt_offset,
                )),
            )
            for salt_offset in range(limit)
        ]
    )


SYSTEM_HANDLERS: dict[int, Callable[[Client, Message, Session], Awaitable[RpcResult | Pong | None]]] = {
    MsgsAck.tlid(): msgs_ack,
    Ping.tlid(): ping,
    PingDelayDisconnect.tlid(): ping_delay_disconnect,
    InvokeWithLayer.tlid(): invoke_with_layer,
    InvokeAfterMsg.tlid(): invoke_after_msg,
    InvokeWithoutUpdates.tlid(): invoke_without_updates,
    InitConnection.tlid(): init_connection,
    DestroySession.tlid(): destroy_session,
    RpcDropAnswer.tlid(): rpc_drop_answer,
    GetFutureSalts.tlid(): get_future_salts,
}
