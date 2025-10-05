from __future__ import annotations

from asyncio import get_running_loop
from datetime import datetime
from time import time
from typing import TYPE_CHECKING, Awaitable, Callable

from loguru import logger

from piltover.db.models import UserAuthorization, ServerSalt, AuthKey
from piltover.session_manager import Session
from piltover.tl import InitConnection, MsgsAck, Ping, Pong, PingDelayDisconnect, InvokeWithLayer, InvokeAfterMsg, \
    InvokeWithoutUpdates, RpcDropAnswer, DestroySession, DestroySessionOk, RpcAnswerUnknown, GetFutureSalts, FutureSalts
from piltover.tl.core_types import Message, RpcResult

if TYPE_CHECKING:
    from piltover.gateway import Client


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
    if request.obj.layer > client.layer:
        # TODO: only same layer if inner query is InitConnection?
        await AuthKey.filter(id=client.auth_data.perm_auth_key_id).update(layer=client.layer)
    client.layer = request.obj.layer
    return await _invoke_inner_query(client, request, session)


async def invoke_after_msg(client: Client, request: Message[InvokeAfterMsg], session: Session) -> RpcResult:
    return await _invoke_inner_query(client, request, session)


async def invoke_without_updates(client: Client, request: Message[InvokeWithoutUpdates], session: Session) -> RpcResult:
    client.no_updates = True
    return await _invoke_inner_query(client, request, session)


async def init_connection(client: Client, request: Message[InitConnection], session: Session) -> RpcResult:
    # hmm yes yes, I trust you client
    # the api id is always correct, it has always been!
    authorization = await UserAuthorization.get_or_none(key__id=client.auth_data.perm_auth_key_id)
    if authorization is not None:
        # TODO: set api id
        authorization.active_at = datetime.now()
        authorization.device_model = request.obj.device_model
        authorization.system_version = request.obj.system_version
        authorization.app_version = request.obj.app_version
        authorization.ip = client.peername[0]

        if not client.no_updates:
            ...  # TODO: subscribe user to updates manually

    logger.info(f"initConnection with Api ID: {request.obj.api_id}")

    return await _invoke_inner_query(client, request, session)


# noinspection PyUnusedLocal
async def destroy_session(client: Client, request: Message[DestroySession], session: Session) -> DestroySessionOk:
    return DestroySessionOk(session_id=request.obj.session_id)


# noinspection PyUnusedLocal
async def rpc_drop_answer(client: Client, request: Message[RpcDropAnswer], session: Session) -> RpcResult:
    return RpcResult(req_msg_id=request.message_id, result=RpcAnswerUnknown())


async def get_future_salts(_1: Client, request: Message[GetFutureSalts], _2: Session) -> FutureSalts:
    limit = max(min(request.obj.num, 1), 64)
    base_id = int(time() // (60 * 60))

    exists = set(await ServerSalt.filter(id__gt=base_id).limit(limit).values_list("id", flat=True))
    to_create = set(range(base_id + 1, base_id + limit + 1)) - exists
    if to_create:
        await ServerSalt.bulk_create([
            ServerSalt(id=create_id)
            for create_id in to_create
        ])

    salts = await ServerSalt.filter(id__gt=base_id).limit(limit)

    return FutureSalts(
        req_msg_id=request.message_id,
        now=int(time()),
        salts=[salt.to_tl() for salt in salts]
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
