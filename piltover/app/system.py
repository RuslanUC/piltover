from datetime import datetime

from piltover.db.models import UserAuthorization
from piltover.server import MessageHandler, Client
from piltover.tl.types import CoreMessage
from piltover.tl_new import InitConnection, MsgsAck, Ping, Pong, PingDelayDisconnect, InvokeWithLayer, InvokeAfterMsg, \
    InvokeWithoutUpdates, SetClientDHParams, RpcDropAnswer, DestroySession, DestroySessionOk, RpcAnswerUnknown

handler = MessageHandler("system")


# noinspection PyUnusedLocal
@handler.on_message(MsgsAck)
async def msgs_ack(client: Client, request: CoreMessage[MsgsAck], session_id: int):
    # print(request.obj, request.message_id)
    return True


# noinspection PyUnusedLocal
@handler.on_message(Ping)
async def pong(client: Client, request: CoreMessage[Ping], session_id: int):
    return Pong(msg_id=request.message_id, ping_id=request.obj.ping_id)


# noinspection PyUnusedLocal
@handler.on_message(PingDelayDisconnect)
async def ping_delay_disconnect(client: Client, request: CoreMessage[PingDelayDisconnect], session_id: int):
    # TODO: disconnect
    return Pong(msg_id=request.message_id, ping_id=request.obj.ping_id)


@handler.on_message(InvokeWithLayer)
async def invoke_with_layer(client: Client, request: CoreMessage[InvokeWithLayer], session_id: int):
    client.layer = request.obj.layer
    return await client.propagate(
        CoreMessage(
            obj=request.obj.query,
            message_id=request.message_id,
            seq_no=request.seq_no,
        ),
        session_id,
    )


@handler.on_message(InvokeAfterMsg)
async def invoke_after_msg(client: Client, request: CoreMessage[InvokeAfterMsg], session_id: int):
    return await client.propagate(
        CoreMessage(
            obj=request.obj.query,
            message_id=request.message_id,
            seq_no=request.seq_no,
        ),
        session_id,
    )


@handler.on_message(InvokeWithoutUpdates)
async def invoke_without_updates(client: Client, request: CoreMessage[InvokeWithoutUpdates], session_id: int):
    return await client.propagate(
        CoreMessage(
            obj=request.obj.query,
            message_id=request.message_id,
            seq_no=request.seq_no,
        ),
        session_id,
    )


@handler.on_message(InitConnection)
async def init_connection(client: Client, request: CoreMessage[InitConnection], session_id: int):
    # hmm yes yes, I trust you client
    # the api id is always correct, it has always been!
    await UserAuthorization.filter(key__id=str(client.auth_data.auth_key_id)).update(
        active_at=datetime.now(),
        device_model=request.obj.device_model,
        system_version=request.obj.system_version,
        app_version=request.obj.app_version,
        # TODO: set ip and api id
    )

    print("initConnection with Api ID:", request.obj.api_id)

    return await client.propagate(
        CoreMessage(
            obj=request.obj.query,
            message_id=request.message_id,
            seq_no=request.seq_no,
        ),
        session_id,
    )


# noinspection PyUnusedLocal
@handler.on_message(SetClientDHParams)
async def set_client_dh_params(client: Client, request: CoreMessage[SetClientDHParams], session_id: int):
    # print(request.obj)
    # print(client.shared)
    raise


# noinspection PyUnusedLocal
@handler.on_message(DestroySession)
async def destroy_session(client: Client, request: CoreMessage[DestroySession], session_id: int):
    return DestroySessionOk(session_id=request.obj.session_id)


# noinspection PyUnusedLocal
@handler.on_message(RpcDropAnswer)
async def rpc_drop_answer(client: Client, request: CoreMessage[RpcDropAnswer], session_id: int):
    return RpcAnswerUnknown()
