import asyncio
from io import BytesIO
from os import environ
from time import time

from loguru import logger
from mtproto import Connection, ConnectionRole
from mtproto.packets import MessagePacket, EncryptedMessagePacket, UnencryptedMessagePacket, DecryptedMessagePacket, \
    ErrorPacket, QuickAckPacket, BasePacket
from taskiq import AsyncTaskiqTask, TaskiqResult, TaskiqEvents
from taskiq.kicker import AsyncKicker

from piltover._keygen_handlers import KEYGEN_HANDLERS
from piltover._system_handlers import SYSTEM_HANDLERS
from piltover.cache import Cache
from piltover.message_brokers.base_broker import BrokerType
from piltover.message_brokers.rabbitmq_broker import RabbitMqMessageBroker
from piltover.utils.utils import run_coro_with_additional_return

try:
    from taskiq_aio_pika import AioPikaBroker
    from taskiq_redis import RedisAsyncResultBackend

    REMOTE_BROKER_SUPPORTED = True
except ImportError:
    AioPikaBroker = None
    RedisAsyncResultBackend = None
    REMOTE_BROKER_SUPPORTED = False

from piltover.auth_data import AuthData, GenAuthData
from piltover.db.models import AuthKey, TempAuthKey, UserAuthorization, ChatParticipant, ServerSalt
from piltover.exceptions import Disconnection, InvalidConstructorException
from piltover.session_manager import Session, SessionManager, MsgIdValues
from piltover.tl import TLObject, SerializationUtils, NewSessionCreated, BadServerSalt, BadMsgNotification, Long, Int, \
    RpcError, Vector
from piltover.tl.core_types import MsgContainer, Message, RpcResult
from piltover.tl.functions.auth import BindTempAuthKey
from piltover.utils import gen_keys, get_public_key_fingerprint, load_private_key, load_public_key, background, Keys
from piltover.tl.functions.internal import CallRpc
from piltover.tl.types.internal import RpcResponse


class Gateway:
    HOST = "0.0.0.0"
    PORT = 4430
    RMQ_HOST = "amqp://guest:guest@127.0.0.1:5672"
    REDIS_HOST = "redis://127.0.0.1"
    TL_CHECK_RESPONSES = environ.get("TL_DEBUG_CHECK_RESPONSES", "").lower() in ("1", "true",)

    def __init__(
            self, host: str = HOST, port: int = PORT, server_keys: Keys | None = None,
            rabbitmq_address: str | None = RMQ_HOST, redis_address: str | None = REDIS_HOST,
    ):
        self.host = host
        self.port = port

        self.server_keys = server_keys
        if self.server_keys is None:
            self.server_keys = gen_keys()

        self.public_key = load_public_key(self.server_keys.public_key)
        self.private_key = load_private_key(self.server_keys.private_key)

        self.fingerprint: int = get_public_key_fingerprint(self.server_keys.public_key)

        self.clients: dict[str, Client] = {}

        self.salt_id = 0
        self.salt = b"\x00" * 8

        if not REMOTE_BROKER_SUPPORTED or rabbitmq_address is None or redis_address is None:
            logger.info("rabbitmq_address or redis_address is None, falling back to worker broker")
            from piltover.worker import Worker
            self.worker = Worker(self.server_keys, None, None)
            self.broker = self.worker.broker
            self.message_broker = self.worker.message_broker
        else:
            logger.debug("Using AioPikaBroker + RedisAsyncResultBackend")
            self.worker = None
            self.broker = AioPikaBroker(rabbitmq_address).with_result_backend(RedisAsyncResultBackend(redis_address))
            self.message_broker = RabbitMqMessageBroker(BrokerType.READ, rabbitmq_address)
            self.broker.add_event_handler(TaskiqEvents.WORKER_STARTUP, self._broker_startup)
            self.broker.add_event_handler(TaskiqEvents.WORKER_STARTUP, self._broker_shutdown)

    async def _broker_startup(self, _) -> None:
        await self.message_broker.startup()
        SessionManager.set_broker(self.message_broker)

    async def _broker_shutdown(self, _) -> None:
        await self.message_broker.shutdown()

    @logger.catch
    async def accept_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        client = Client(server=self, reader=reader, writer=writer)
        background(client.worker())

    async def serve(self):
        await self.broker.startup()
        server = await asyncio.start_server(self.accept_client, self.host, self.port)
        async with server:
            await server.serve_forever()

    @staticmethod
    async def get_auth_key(auth_key_id: int) -> tuple[int, bytes, bool] | None:
        logger.debug(f"Requested auth key: {auth_key_id}")
        if key := await AuthKey.get_or_temp(auth_key_id):
            return auth_key_id, key.auth_key, isinstance(key, TempAuthKey)

    async def get_current_salt(self) -> bytes:
        current_id = int(time() // (60 * 60))
        if self.salt_id != current_id:
            logger.debug("Current salt is expired, fetching new one")
            salt, _ = await ServerSalt.get_or_create(id=current_id)
            self.salt_id = salt.id
            self.salt = Long.write(salt.salt)

        return self.salt


class Client:
    __slots__ = (
        "server", "reader", "writer", "conn", "peername", "auth_data", "empty_session", "session", "no_updates",
        "layer", "authorization", "disconnect_timeout", "channels_loaded_at", "msg_id_values",
    )

    def __init__(self, server: Gateway, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        self.server = server

        self.reader = reader
        self.writer = writer
        self.conn = Connection(role=ConnectionRole.SERVER)
        self.peername: tuple[str, int] = writer.get_extra_info("peername")

        self.auth_data: AuthData | GenAuthData | None = None
        self.empty_session = Session(self, 0, MsgIdValues())
        self.session: Session | None = None
        self.msg_id_values = MsgIdValues()
        self.authorization: tuple[UserAuthorization | None, int | float] = (None, 0)
        self.channels_loaded_at = 0.0

        self.no_updates = False
        self.layer = 136

        self.disconnect_timeout: asyncio.Timeout | None = None

    def _get_session(self, session_id: int) -> tuple[Session, bool]:
        if self.session is not None:
            if self.session.session_id == session_id:
                return self.session, False
            self.session.destroy()

        self.session, created = SessionManager.get_or_create(self, session_id, self.msg_id_values)
        if not created and self.session.online:
            self.session.destroy()
            return self._get_session(session_id)

        return self.session, created

    async def read_packet(self) -> MessagePacket | None:
        packet = self.conn.receive()
        if isinstance(packet, MessagePacket):
            return packet

        recv = await self.reader.read(32 * 1024)
        if not recv:
            raise Disconnection

        packet = self.conn.receive(recv)
        if not isinstance(packet, MessagePacket):
            return None

        return packet

    async def _write(self, packet: BasePacket) -> None:
        to_send = self.conn.send(packet)
        self.writer.write(to_send)
        await self.writer.drain()

    async def _send_raw(self, message: Message, session: Session) -> None:
        if not self.auth_data or self.auth_data.auth_key is None or self.auth_data.auth_key_id is None:
            logger.error("Trying to send encrypted response, but auth_key is empty")
            raise Disconnection(404)

        logger.debug(f"Sending to {self.session.session_id if self.session else 0}: {message}")

        if self.server.TL_CHECK_RESPONSES:
            try:
                obj_cls = type(message.obj)
                obj_write = message.obj.write()
                obj_read = obj_cls.read(BytesIO(obj_write), True)
                message.obj.eq_raise(obj_read)
            except Exception as e:
                logger.opt(exception=e).warning(
                    "Failed response check! "
                    "(It may fail on correct data when reading Bool because it is not in all.object "
                    "or Vector because when serialized, it doesn't have any type information)"
                )

        encrypted = DecryptedMessagePacket(
            salt=await self.server.get_current_salt(),
            session_id=session.session_id,
            message_id=message.message_id,
            seq_no=message.seq_no,
            data=message.obj.write(),
        ).encrypt(self.auth_data.auth_key, ConnectionRole.SERVER)

        await self._write(encrypted)

    async def send(
            self, obj: TLObject, session: Session, originating_request: Message | DecryptedMessagePacket | None = None
    ) -> None:
        message = session.pack_message(obj, originating_request)

        await self._send_raw(message, session)

    async def send_container(self, objects: list[tuple[TLObject, Message]], session: Session):
        logger.debug(f"Sending: {objects}")
        message = session.pack_container(objects)

        await self._send_raw(message, session)

    async def send_unencrypted(self, obj: TLObject) -> None:
        logger.debug(obj)
        await self._write(UnencryptedMessagePacket(
            self.empty_session.msg_id(in_reply=True),
            obj.write(),
        ))

    async def _kiq(
            self, obj: TLObject, session: Session, message_id: int | None = None
    ) -> AsyncTaskiqTask:
        auth_key_id = (self.auth_data.auth_key_id or None) if self.auth_data else None
        is_temp = self.auth_data.is_temp if self.auth_data and auth_key_id else False

        auth_id = None
        user_id = None

        if auth_key_id is not None:
            auth, loaded_at = self.authorization
            if auth is None or (time() - loaded_at) > 60:
                query_key = "key__tempauthkeys__id" if is_temp else "key__id"
                query = {query_key: str(auth_key_id)}

                auth = await UserAuthorization.get_or_none(**query).select_related("user")

                self.authorization = (auth, time())
                if auth is not None and session.user_id is None:
                    session.set_user_id(auth.user.id)

            auth_id = auth.id if auth is not None else None
            user_id = auth.user.id if auth is not None else None

            if auth is not None and (time() - self.channels_loaded_at) > 60 * 5:
                channel_ids: Vector[Long] | None = await Cache.obj.get(f"channels:{auth.user.id}")
                if channel_ids is None:
                    channel_ids: list[Long] = [
                        Long(channel_id)
                        async for channel_id in ChatParticipant.filter(
                            channel_id__not_isnull=True, user=auth.user
                        ).values_list("channel_id", flat=True)
                    ]
                    await Cache.obj.set(f"channels:{auth.user.id}", channel_ids, ttl=60 * 10)

                channel_ids: list[int] = list(map(int, channel_ids))
                old_channels = set(session.channel_ids)
                new_channels = set(channel_ids)
                channels_to_delete = old_channels - new_channels
                channels_to_add = new_channels - old_channels

                SessionManager.broker.channels_diff_update(session, channels_to_delete, channels_to_add)

            old_auth_id = session.auth_id
            if old_auth_id != auth_id:
                session.auth_id = auth_id
                SessionManager.broker.unsubscribe_auth(old_auth_id, session)
                SessionManager.broker.subscribe_auth(auth_id, session)

         # TODO: dont do .write.hex(), RpcResponse somehow dont need encoding it manually, check how exactly
        return await AsyncKicker(task_name=f"handle_tl_rpc", broker=self.server.broker, labels={}).kiq(CallRpc(
            obj=obj,
            layer=self.layer,
            key_is_temp=is_temp,
            auth_key_id=auth_key_id,
            session_id=session.session_id if session is not None else None,
            message_id=message_id,
            auth_id=auth_id,
            user_id=user_id,
        ).write().hex())

    async def handle_unencrypted_message(self, obj: TLObject):
        # TODO: move it to worker (and add db models to save auth key generation state)
        if obj.tlid() in KEYGEN_HANDLERS:
            await KEYGEN_HANDLERS[obj.tlid()](self, obj)

        #if not isinstance(obj, (ReqPqMulti, ReqPq, ReqDHParams, SetClientDHParams, MsgsAck)):
        #    logger.debug(f"Received unexpected unencrypted message: {obj}")
        #    raise Disconnection(404)

        #task = await self._kiq(obj)
        #result: RpcResponse = await task.wait_result(timeout=5)
        #if result.transport_error is not None:
        #    raise Disconnection(result.transport_error or None)
        #if result.obj is not None:
        #    await self.send_unencrypted(result.obj)

    async def handle_encrypted_message(self, req_message: Message, session: Session):
        if isinstance(req_message.obj, MsgContainer):
            results = []
            tasks = [
                run_coro_with_additional_return(self.propagate(msg, session), msg)
                for msg in req_message.obj.messages
            ]
            for task_result in asyncio.as_completed(tasks):
                result, msg = await task_result
                if result is None:
                    continue
                results.append((result, msg))

            if not results:
                logger.warning("Empty msg_container, returning...")
                return

            return await self.send_container(results, session)

        if (result := await self.propagate(req_message, session)) is None:
            return

        await self.send(result, session, originating_request=req_message)

    # https://core.telegram.org/mtproto/service_messages_about_messages#notice-of-ignored-error-message
    async def _is_message_bad(self, packet: DecryptedMessagePacket, check_salt: bool) -> bool:
        error_code = 0

        if packet.message_id % 4 != 0:
            # 18: incorrect two lower order msg_id bits (the server expects client message msg_id to be divisible by 4)
            logger.debug(f"Client sent message id which is not divisible by 4")
            error_code = 18
        elif (packet.message_id >> 32) < (time() - 300):
            # 16: msg_id too low
            logger.debug(f"Client sent message id which is too low")
            error_code = 16
        elif (packet.message_id >> 32) < (time() - 300):
            # 16: msg_id too high
            logger.debug(f"Client sent message id which is too low")
            error_code = 17

        # TODO: add validation for message_id duplication (code 19)
        # TODO: add validation for seq_no too low/high (code 32 and 33)
        # TODO: add validation for seq_no even/odd (code 34 and 35)

        if error_code:
            await self.send(
                BadMsgNotification(
                    bad_msg_id=packet.message_id,
                    bad_msg_seqno=packet.seq_no,
                    error_code=error_code,
                ),
                Session(self, packet.session_id, self.msg_id_values),
                packet,
            )
            return True

        # 48: incorrect server salt (in this case, the bad_server_salt response is received with the correct salt,
        # and the message is to be re-sent with it)
        if check_salt and packet.salt != await self.server.get_current_salt():
            logger.debug(
                f"Client sent bad salt ({int.from_bytes(packet.salt, 'little')}) "
                f"in message {packet.message_id}, sending correct salt"
            )
            await self.send(
                BadServerSalt(
                    bad_msg_id=packet.message_id,
                    bad_msg_seqno=packet.seq_no,
                    error_code=48,
                    new_server_salt=Long.read_bytes(await self.server.get_current_salt()),
                ),
                Session(self, packet.session_id, self.msg_id_values),
                packet,
            )
            return True

        return False

    async def recv(self):
        packet = await self.read_packet()

        if isinstance(packet, EncryptedMessagePacket):
            decrypted = await self.decrypt(packet)
            if packet.needs_quick_ack:
                await self._write(self._create_quick_ack(decrypted))

            # For some reason some clients cant process BadServerSalt response to BindTempAuthKey request
            if await self._is_message_bad(decrypted, decrypted.data[:4] != Int.write(BindTempAuthKey.tlid(), False)):
                return

            message = Message(
                message_id=decrypted.message_id,
                seq_no=decrypted.seq_no,
                obj=TLObject.read(BytesIO(decrypted.data)),
            )

            session, created = self._get_session(decrypted.session_id)
            session.update_incoming_content_related_msgs(message.obj, message.seq_no)
            if created:
                logger.info(f"({self.peername}) Created session {session.session_id}")
                await self.send(
                    NewSessionCreated(
                        first_msg_id=message.message_id,
                        unique_id=session.session_id,
                        server_salt=Long.read_bytes(await self.server.get_current_salt()),
                    ),
                    session,
                )

            logger.debug(f"Received from {self.session.session_id if self.session else 0}: {message}")
            asyncio.create_task(self.handle_encrypted_message(message, session))
        elif isinstance(packet, UnencryptedMessagePacket):
            decoded = SerializationUtils.read(BytesIO(packet.message_data), TLObject)
            logger.debug(decoded)
            await self.handle_unencrypted_message(decoded)

    async def _set_auth_data(self, auth_key_id: int) -> None:
        if self.auth_data is None or not self.auth_data.check_key(auth_key_id):
            got = await self.server.get_auth_key(auth_key_id)
            if got is None:
                logger.info(f"Client ({self.peername}) sent unknown auth_key_id {auth_key_id}, disconnecting with 404")
                raise Disconnection(404)
            self.auth_data = AuthData(*got)

    def _create_quick_ack(self, message: DecryptedMessagePacket) -> QuickAckPacket:
        return message.quick_ack_response(self.auth_data.auth_key, ConnectionRole.CLIENT)

    async def decrypt(self, message: EncryptedMessagePacket, v1: bool = False) -> DecryptedMessagePacket:
        await self._set_auth_data(message.auth_key_id)

        try:
            return message.decrypt(self.auth_data.auth_key, ConnectionRole.CLIENT, v1)
        except ValueError:
            logger.info("Failed to decrypt encrypted packet, disconnecting with 404")
            raise Disconnection(404)

    async def _worker_loop(self) -> None:
        while True:
            try:
                await self.recv()
            except AssertionError:
                logger.exception("Unexpected failed assertion", backtrace=True)
            except InvalidConstructorException as e:
                if e.wrong_type:
                    continue

                logger.error(
                    f"Invalid constructor: {e.constructor} ({hex(e.constructor)[2:]}), "
                    f"leftover bytes={e.leftover_bytes}"
                )

                raise Disconnection(400)

    @logger.catch
    async def worker(self):
        logger.debug(f"Client connected: {self.peername}")

        try:
            async with asyncio.timeout(None) as self.disconnect_timeout:
                await self._worker_loop()
        except Disconnection as err:
            if err.transport_error is not None:
                await self._write(ErrorPacket(err.transport_error))
        except TimeoutError:
            logger.debug("Client disconnected because of expired timeout")
        finally:
            logger.info("Client disconnected")

            self.writer.close()
            await self.writer.wait_closed()

            if self.session is not None:
                logger.info(f"Session {self.session.session_id} removed")
                self.session.destroy()

    async def propagate(self, request: Message, session: Session) -> RpcResult | None:
        if request.obj.tlid() in SYSTEM_HANDLERS:
            return await SYSTEM_HANDLERS[request.obj.tlid()](self, request, session)

        task = await self._kiq(request.obj, session, request.message_id)
        task_result: TaskiqResult[str] = await task.wait_result(timeout=5)
        if task_result.is_err:
            logger.opt(exception=task_result.error).error("An error occurred in worker while processing request.")
            return RpcResult(
                req_msg_id=request.message_id,
                result=RpcError(error_code=500, error_message="INTERNAL_SERVER_ERROR"),
            )

        result = task_result.return_value
        if not isinstance(result, RpcResponse):
            logger.error(f"Got response from worker that is not a RpcResponse object: {result}")
            return RpcResult(
                req_msg_id=request.message_id,
                result=RpcError(error_code=500, error_message="INTERNAL_SERVER_ERROR"),
            )

        if result.transport_error is not None:
            raise Disconnection(result.transport_error or None)

        return result.obj
