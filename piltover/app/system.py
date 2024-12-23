from datetime import datetime
from time import time

from loguru import logger

from piltover.db.models import UserAuthorization
from piltover.db.models.server_salt import ServerSalt
from piltover.server import MessageHandler, Client
from piltover.session_manager import Session
from piltover.tl import InitConnection, MsgsAck, Ping, Pong, PingDelayDisconnect, InvokeWithLayer, InvokeAfterMsg, \
    InvokeWithoutUpdates, RpcDropAnswer, DestroySession, DestroySessionOk, RpcAnswerUnknown, GetFutureSalts, FutureSalts
from piltover.tl.core_types import Message

handler = MessageHandler("system")


# noinspection PyUnusedLocal
@handler.on_message(MsgsAck)
async def msgs_ack(client: Client, request: Message[MsgsAck], session: Session):
    return False # True


# noinspection PyUnusedLocal
@handler.on_message(Ping)
async def pong(client: Client, request: Message[Ping], session: Session):
    return Pong(msg_id=request.message_id, ping_id=request.obj.ping_id)


# noinspection PyUnusedLocal
@handler.on_message(PingDelayDisconnect)
async def ping_delay_disconnect(client: Client, request: Message[PingDelayDisconnect], session: Session):
    # TODO: disconnect
    return Pong(msg_id=request.message_id, ping_id=request.obj.ping_id)


@handler.on_message(InvokeWithLayer)
async def invoke_with_layer(client: Client, request: Message[InvokeWithLayer], session: Session):
    client.layer = request.obj.layer
    return await client.propagate(
        Message(
            obj=request.obj.query,
            message_id=request.message_id,
            seq_no=request.seq_no,
        ),
        session,
    )


@handler.on_message(InvokeAfterMsg)
async def invoke_after_msg(client: Client, request: Message[InvokeAfterMsg], session: Session):
    return await client.propagate(
        Message(
            obj=request.obj.query,
            message_id=request.message_id,
            seq_no=request.seq_no,
        ),
        session,
    )


@handler.on_message(InvokeWithoutUpdates)
async def invoke_without_updates(client: Client, request: Message[InvokeWithoutUpdates], session: Session):
    client.no_updates = True

    return await client.propagate(
        Message(
            obj=request.obj.query,
            message_id=request.message_id,
            seq_no=request.seq_no,
        ),
        session,
    )


@handler.on_message(InitConnection)
async def init_connection(client: Client, request: Message[InitConnection], session: Session):
    # hmm yes yes, I trust you client
    # the api id is always correct, it has always been!
    authorization = await UserAuthorization.get_or_none(key__id=str(await client.auth_data.get_perm_id()))
    if authorization is not None:
        # TODO: set api id
        authorization.active_at = datetime.now()
        authorization.device_model = request.obj.device_model
        authorization.system_version = request.obj.system_version
        authorization.app_version = request.obj.app_version
        authorization.ip = client.peername[0]

        if not client.no_updates:
            ...  # TODO: subscribe user to updates

    logger.info(f"initConnection with Api ID: {request.obj.api_id}")

    return await client.propagate(
        Message(
            obj=request.obj.query,
            message_id=request.message_id,
            seq_no=request.seq_no,
        ),
        session,
    )


# noinspection PyUnusedLocal
@handler.on_message(DestroySession)
async def destroy_session(client: Client, request: Message[DestroySession], session: Session):
    return DestroySessionOk(session_id=request.obj.session_id)


# noinspection PyUnusedLocal
@handler.on_message(RpcDropAnswer)
async def rpc_drop_answer(client: Client, request: Message[RpcDropAnswer], session: Session):
    return RpcAnswerUnknown()


# noinspection PyUnusedLocal
@handler.on_message(GetFutureSalts)
async def get_future_salts(client: Client, request: Message[GetFutureSalts], session: Session):
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
