from __future__ import annotations

import asyncio
import base64
import os
from io import BytesIO
from pathlib import Path
from time import time
from typing import TYPE_CHECKING

from loguru import logger
from lru import LRU
from mtproto import Connection, ConnectionRole
from mtproto.packets import MessagePacket, EncryptedMessagePacket, UnencryptedMessagePacket, DecryptedMessagePacket, \
    ErrorPacket, QuickAckPacket, BasePacket
from taskiq import AsyncTaskiqTask, TaskiqResult, TaskiqEvents, AsyncBroker
from taskiq.kicker import AsyncKicker
from tortoise.expressions import Q

try:
    from taskiq_aio_pika import AioPikaBroker
    from taskiq_redis import RedisAsyncResultBackend

    REMOTE_BROKER_SUPPORTED = True
except ImportError:
    AioPikaBroker = None
    RedisAsyncResultBackend = None
    REMOTE_BROKER_SUPPORTED = False

from piltover.layer_converter.manager import LayerConverter
from piltover._keygen_handlers import KEYGEN_HANDLERS
from piltover._system_handlers import SYSTEM_HANDLERS
from piltover.context import SerializationContext, ContextValues
from piltover.db.enums import PrivacyRuleKeyType
from piltover.message_brokers.base_broker import BrokerType
from piltover.message_brokers.rabbitmq_broker import RabbitMqMessageBroker
from piltover.tl.utils import is_id_strictly_not_content_related, is_id_strictly_content_related, is_content_related
from piltover.utils.debug import measure_time

from piltover.auth_data import AuthData, GenAuthData
from piltover.db.models import AuthKey, ChatParticipant, Peer, Contact, PrivacyRule, Presence, PollVote, MessageRef
from piltover.exceptions import Disconnection, InvalidConstructorException
from piltover.session import Session
from piltover.session_manager import SessionManager
from piltover.tl import TLObject, NewSessionCreated, BadServerSalt, BadMsgNotification, Long, Int, RpcError, ReqPq, \
    ReqPqMulti
from piltover.tl.core_types import MsgContainer, Message, RpcResult
from piltover.tl.functions.auth import BindTempAuthKey
from piltover.utils import gen_keys, get_public_key_fingerprint, load_private_key, load_public_key, background, Keys
from piltover.tl.functions.internal import CallRpc
from piltover.tl.types.internal import RpcResponse, NeedsContextValues

if TYPE_CHECKING:
    from piltover.worker import Worker
    from piltover.scheduler import Scheduler


class Gateway:
    HOST = "0.0.0.0"
    PORT = 4430
    RMQ_HOST = "amqp://guest:guest@127.0.0.1:5672"
    REDIS_HOST = "redis://127.0.0.1"

    def __init__(
            self, data_dir: Path, host: str = HOST, port: int = PORT, server_keys: Keys | None = None,
            rabbitmq_address: str | None = RMQ_HOST, redis_address: str | None = REDIS_HOST,
            salt_key: bytes | None = None,
    ):
        self.data_dir = data_dir

        self.host = host
        self.port = port

        self.server_keys = server_keys
        if self.server_keys is None:
            self.server_keys = gen_keys()

        self.public_key = load_public_key(self.server_keys.public_key)
        self.private_key = load_private_key(self.server_keys.private_key)

        self.fingerprint: int = get_public_key_fingerprint(self.server_keys.public_key)
        self.fingerprint_signed: int = get_public_key_fingerprint(self.server_keys.public_key, True)

        self.clients: dict[str, Client] = {}

        if salt_key is None:
            salt_key = os.urandom(32)
            logger.info(f"Salt key is None, generating new one: {base64.b64encode(salt_key).decode('latin1')}")

        self.salt_key = salt_key

        self.worker: Worker | None
        self.broker: AsyncBroker | None
        self.scheduler: Scheduler | None

        if not REMOTE_BROKER_SUPPORTED or rabbitmq_address is None or redis_address is None:
            logger.info("rabbitmq_address or redis_address is None, falling back to worker broker")
            from piltover.worker import Worker
            from piltover.scheduler import Scheduler
            self.worker = Worker(data_dir, self.server_keys, None, None)
            self.broker = self.worker.broker
            self.scheduler = Scheduler(None, _broker=self.broker)
            self.message_broker = self.worker.message_broker
        else:
            logger.debug("Using AioPikaBroker + RedisAsyncResultBackend")
            self.worker = None
            self.scheduler = None
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
    async def get_auth_data(auth_key_id: int) -> AuthData | None:
        logger.debug(f"Requested auth key: {auth_key_id}")
        return await AuthKey.get_auth_data(auth_key_id)


class MsgIdValues:
    __slots__ = ("last_time", "offset",)

    def __init__(self, last_time: int = 0, offset: int = 0) -> None:
        self.last_time = last_time
        self.offset = offset


_check_req_pq_tlid = (Int.write(ReqPq.tlid(), False), Int.write(ReqPqMulti.tlid(), False))


class Client:
    __slots__ = (
        "server", "reader", "writer", "conn", "peername", "gen_auth_data", "empty_session", "disconnect_timeout",
        "msg_id_values", "out_seq_no", "write_lock", "active_sessions", "active_keys",
    )

    def __init__(self, server: Gateway, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        self.server = server

        self.reader = reader
        self.writer = writer
        self.conn = Connection(role=ConnectionRole.SERVER)
        self.peername: tuple[str, int] = writer.get_extra_info("peername")

        self.gen_auth_data: GenAuthData | None = None
        self.empty_session = Session(0)
        self.msg_id_values = MsgIdValues()
        self.out_seq_no = 0

        self.disconnect_timeout: asyncio.Timeout | None = None
        self.write_lock = asyncio.Lock()

        self.active_sessions = LRU(4, callback=self._session_evicted)
        self.active_keys = LRU(8)

    @staticmethod
    def _session_evicted(_: ..., session: Session) -> None:
        session.destroy()

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
        ret = self.out_seq_no * 2
        if is_content_related(obj):
            self.out_seq_no += 1
            ret += 1
        return ret

    # https://core.telegram.org/mtproto/description#message-identifier-msg-id
    def pack_message(self, obj: TLObject, session: Session, in_reply: bool) -> Message:
        try:
            downgraded_maybe = LayerConverter.downgrade(obj, session.layer)
        except Exception as e:
            logger.opt(exception=e).error("Failed to downgrade object")
            raise

        return Message(
            message_id=self.msg_id(in_reply=in_reply),
            seq_no=self.get_outgoing_seq_no(obj),
            obj=downgraded_maybe,
        )

    # https://core.telegram.org/mtproto/description#message-identifier-msg-id
    def pack_container(self, objects: list[tuple[TLObject, bool]], session: Session) -> Message:
        container = MsgContainer(messages=[
            Message(
                message_id=self.msg_id(in_reply=in_reply),
                seq_no=self.get_outgoing_seq_no(obj),
                obj=obj,
            )
            for obj, in_reply in objects
        ])

        return self.pack_message(container, session, False)

    def _get_cached_session(self, auth_key_id: int, session_id: int) -> Session | None:
        uniq_id = (auth_key_id, session_id)
        if uniq_id in self.active_sessions:
            return self.active_sessions[uniq_id]

    def _get_session(self, session_id: int, auth_data: AuthData) -> tuple[Session, bool]:
        if (cached := self._get_cached_session(auth_data.auth_key_id, session_id)) is not None:
            return cached, False

        session, created = SessionManager.get_or_create(session_id, self, auth_data)
        session.set_client(self)

        self.active_sessions[session.uniq_id()] = session
        return session, created

    def _disconnect_if_invalid_packet_length(self) -> None:
        if (packet_len := self.conn.peek_length()) is not None and packet_len >= 1024 * 1024:
            raise Disconnection

    async def read_packet(self) -> MessagePacket | None:
        self._disconnect_if_invalid_packet_length()

        packet = self.conn.receive()
        if isinstance(packet, MessagePacket):
            return packet

        recv = await self.reader.read(32 * 1024)
        if not recv:
            raise Disconnection

        packet = self.conn.receive(recv)
        if not isinstance(packet, MessagePacket):
            self._disconnect_if_invalid_packet_length()
            return None

        return packet

    async def _write_packet(self, packet: BasePacket, ignore_errors: bool = False) -> None:
        to_send = self.conn.send(packet)
        try:
            async with self.write_lock:
                self.writer.write(to_send)
                await self.writer.drain()
        except ConnectionResetError:
            if ignore_errors:
                return
            raise Disconnection
        except Exception as e:
            if ignore_errors:
                return
            raise Disconnection from e

    async def _send_message(
            self, message: Message, session: Session, context_values: ContextValues | None = None,
    ) -> None:
        if not session.auth_data or session.auth_data.auth_key is None:
            # TODO: this is probably unreachable?
            logger.error("Trying to send encrypted response, but auth_key is empty")
            raise Disconnection(404)

        logger.debug(f"Sending to {session.session_id}: {message!r}")

        auth_id = session.auth_id
        user_id = session.user_id
        logger.debug(f"SerializationContext ({self.peername}): {user_id=}, {auth_id=}")

        session.update_salts_maybe(self.server.salt_key)

        with SerializationContext(auth_id=auth_id, user_id=user_id, layer=session.layer, values=context_values).use():
            decrypted = DecryptedMessagePacket(
                salt=session.salt_now.salt,
                session_id=session.session_id,
                message_id=message.message_id,
                seq_no=message.seq_no,
                data=message.obj.write(),
            )

        encrypted = decrypted.encrypt(session.auth_data.auth_key, ConnectionRole.SERVER)

        await self._write_packet(encrypted)

    async def send(self, obj: TLObject, session: Session, in_reply: bool) -> None:
        with measure_time(".send(...)"):
            context_values = None
            if isinstance(obj, NeedsContextValues):
                with measure_time("._resolve_context_values(...)"):
                    context_values = await self._resolve_context_values(obj, session)
                obj = obj.obj

            with measure_time("session.pack_message(...)"):
                message = self.pack_message(obj, session, in_reply)
            with measure_time("._send_message()"):
                await self._send_message(message, session, context_values)

    async def send_container(self, objects: list[tuple[TLObject, bool]], session: Session):
        logger.debug(f"Sending: {objects}")
        message = self.pack_container(objects, session)
        await self._send_message(message, session)

    async def send_unencrypted(self, obj: TLObject) -> None:
        logger.debug(obj)
        await self._write_packet(UnencryptedMessagePacket(
            self.msg_id(in_reply=True),
            obj.write(),
        ))

    async def _kiq(self, obj: TLObject, session: Session, message_id: int | None = None) -> AsyncTaskiqTask:
        with measure_time("session.refresh_auth_maybe()"):
            await session.refresh_auth_maybe()

        # TODO: dont do .write.hex(), RpcResponse somehow doesn't need encoding it manually, check how exactly
        call_rpc = CallRpc(
            obj=obj,
            layer=session.layer,
            auth_key_id=session.auth_data.auth_key_id,
            perm_auth_key_id=session.auth_data.perm_auth_key_id,
            session_id=session.session_id,
            message_id=message_id,
            auth_id=session.auth_id,
            user_id=session.user_id,
            is_bot=session.is_bot,
            mfa_pending=session.mfa_pending,
        ).write().hex()

        with measure_time(".kiq()"):
            return await AsyncKicker(task_name=f"handle_tl_rpc", broker=self.server.broker, labels={}).kiq(call_rpc)

    async def handle_unencrypted_message(self, obj: TLObject) -> None:
        # TODO: move it to worker (and add db models to save auth key generation state)
        if obj.tlid() not in KEYGEN_HANDLERS:
            return

        try:
            await KEYGEN_HANDLERS[obj.tlid()](self, obj)
        except Disconnection as d:
            logger.opt(exception=d).warning(f"Requested disconnection while processing {obj.tlname()}")
            raise
        except Exception as e:
            logger.opt(exception=e).warning(f"Error while processing {obj.tlname()}")

    async def handle_encrypted_message(self, req_message: Message, session: Session) -> None:
        if isinstance(req_message.obj, MsgContainer):
            await asyncio.gather(*[
                self.propagate(msg, session)
                for msg in req_message.obj.messages
            ])
        else:
            await self.propagate(req_message, session)

    # https://core.telegram.org/mtproto/service_messages_about_messages#notice-of-ignored-error-message
    async def _is_message_bad(self, packet: DecryptedMessagePacket, session: Session, check_salt: bool) -> bool:
        error_code = 0
        inner_id = Int.read_bytes(packet.data[:4], False)

        if packet.message_id % 4 != 0:
            # 18: incorrect two lower order msg_id bits (the server expects client message msg_id to be divisible by 4)
            logger.debug(f"Client sent message id which is not divisible by 4")
            error_code = 18
        elif (packet.message_id >> 32) < (time() - 300):
            # 16: msg_id too low
            logger.debug(f"Client sent message id which is too low")
            error_code = 16
        elif (packet.message_id >> 32) > (time() + 30):
            # 17: msg_id too high
            logger.debug(f"Client sent message id which is too low")
            error_code = 17
        elif (packet.seq_no & 1) == 1 and is_id_strictly_not_content_related(inner_id):
            # 34: an even msg_seqno expected (irrelevant message), but odd received
            logger.debug(f"Client sent odd seq_no for content-related message ({hex(inner_id)[2:]})")
            error_code = 34
        elif (packet.seq_no & 1) == 0 and is_id_strictly_content_related(inner_id):
            # 35: odd msg_seqno expected (relevant message), but even received
            logger.debug(f"Client sent even seq_no for not content-related message ({hex(inner_id)[2:]})")
            error_code = 35

        # TODO: add validation for message_id duplication (code 19)
        # TODO: add validation for seq_no too low/high (code 32 and 33)

        if error_code:
            await self.send(
                obj=BadMsgNotification(
                    bad_msg_id=packet.message_id,
                    bad_msg_seqno=packet.seq_no,
                    error_code=error_code,
                ),
                session=session,
                in_reply=True,
            )
            return True

        # 48: incorrect server salt (in this case, the bad_server_salt response is received with the correct salt,
        # and the message is to be re-sent with it)
        if check_salt and packet.salt not in (session.salt_now.salt, session.salt_prev.salt):
            logger.debug(
                f"Client sent bad salt ({int.from_bytes(packet.salt, 'little')}) "
                f"in message {packet.message_id}, sending correct salt"
            )
            await self.send(
                obj=BadServerSalt(
                    bad_msg_id=packet.message_id,
                    bad_msg_seqno=packet.seq_no,
                    error_code=48,
                    new_server_salt=Long.read_bytes(session.salt_now.salt),
                ),
                session=session,
                in_reply=True,
            )
            return True

        return False

    async def recv(self):
        packet = await self.read_packet()

        if isinstance(packet, EncryptedMessagePacket):
            auth_data = None
            if packet.auth_key_id in self.active_keys:
                auth_key = self.active_keys[packet.auth_key_id]
            else:
                auth_data = await self._get_auth_data(packet.auth_key_id)
                self.active_keys[packet.auth_key_id] = auth_key = auth_data.auth_key

            decrypted = await self.decrypt(packet, auth_key)

            session = self._get_cached_session(packet.auth_key_id, decrypted.session_id)
            if session is None:
                if auth_data is None:
                    auth_data = await self._get_auth_data(packet.auth_key_id)
                session, _ = self._get_session(decrypted.session_id, auth_data)
                session.update_salts_maybe(self.server.salt_key)

            if packet.needs_quick_ack:
                await self._write_packet(self._create_quick_ack(decrypted, session))

            # For some reason some clients cant process BadServerSalt response to BindTempAuthKey request
            check_salt = decrypted.data[:4] != Int.write(BindTempAuthKey.tlid(), False)
            if await self._is_message_bad(decrypted, session, check_salt):
                return

            message = Message(
                message_id=decrypted.message_id,
                seq_no=decrypted.seq_no,
                obj=TLObject.read(BytesIO(decrypted.data)),
            )

            if not session.min_msg_id:
                session.min_msg_id = message.message_id
                await session.fetch_layer()
                logger.info(f"({self.peername}) Created session {session.session_id}")
                await self.send(
                    NewSessionCreated(
                        first_msg_id=message.message_id,
                        unique_id=session.session_id,
                        server_salt=Long.read_bytes(session.salt_now.salt),
                    ),
                    session,
                    False,
                )

            logger.debug(f"Received from {session.session_id}: {message}")
            asyncio.create_task(self.handle_encrypted_message(message, session))
        elif isinstance(packet, UnencryptedMessagePacket):
            decoded = TLObject.read(BytesIO(packet.message_data))
            if isinstance(decoded, (ReqPq, ReqPqMulti)):
                peeked = self.conn.peek_packet()
                packet: UnencryptedMessagePacket | None = None
                while isinstance(peeked, UnencryptedMessagePacket) and peeked.message_data[:4] in _check_req_pq_tlid:
                    logger.debug(f"Skipping reqPQ: {decoded}")
                    packet = self.conn.receive()
                    peeked = self.conn.peek_packet()
                    await asyncio.sleep(0)

                if packet is not None:
                    decoded = TLObject.read(BytesIO(packet.message_data))

            logger.debug(decoded)
            await self.handle_unencrypted_message(decoded)

    async def _get_auth_data(self, auth_key_id: int) -> AuthData:
        data = await self.server.get_auth_data(auth_key_id)
        if data is None:
            logger.info(f"Client ({self.peername}) sent unknown auth_key_id {auth_key_id}, disconnecting with 404")
            raise Disconnection(404)

        return data

    @staticmethod
    def _create_quick_ack(message: DecryptedMessagePacket, session: Session) -> QuickAckPacket:
        return message.quick_ack_response(session.auth_data.auth_key, ConnectionRole.CLIENT)

    @staticmethod
    async def decrypt(message: EncryptedMessagePacket, auth_key: bytes, v1: bool = False) -> DecryptedMessagePacket:
        try:
            return message.decrypt(auth_key, ConnectionRole.CLIENT, v1)
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

                # TODO: does telegram disconnect when invalid constructor is sent
                raise Disconnection(400)

    @logger.catch
    async def worker(self):
        logger.debug(f"Client connected: {self.peername}")

        try:
            async with asyncio.timeout(None) as self.disconnect_timeout:
                await self._worker_loop()
        except Disconnection as err:
            if err.transport_error is not None:
                await self._write_packet(ErrorPacket(err.transport_error), ignore_errors=True)
        except TimeoutError:
            logger.debug("Client disconnected because of expired timeout")
        finally:
            logger.info("Client disconnected")

            self.writer.close()
            await self.writer.wait_closed()

            for session in self.active_sessions.values():
                logger.info(f"Session {session.session_id} removed")
                session.destroy()

            self.active_sessions.clear()

    async def _process_request(self, request: Message, session: Session) -> RpcResult | None:
        if request.obj.tlid() in SYSTEM_HANDLERS:
            return await SYSTEM_HANDLERS[request.obj.tlid()](self, request, session)

        with measure_time("\"execute task\""):
            with measure_time("_kiq()"):
                task = await self._kiq(request.obj, session, request.message_id)
            with measure_time(".wait_result()"):
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

        # logger.trace(f"Got RpcResponse from worker: {result!r}")

        if result.transport_error is not None:
            raise Disconnection(result.transport_error or None)
        if result.refresh_auth:
            await session.refresh_auth_maybe(True)

        return result.obj

    async def propagate(self, request: Message, session: Session) -> RpcResult | None:
        if (result := await self._process_request(request, session)) is not None:
            await self.send(result, session, True)

    # TODO: this method is probably should be between gateway and workers?
    @staticmethod
    async def _resolve_context_values(values: NeedsContextValues, session: Session) -> ContextValues:
        result = ContextValues()

        # TODO: fetch only those values that are actually needed in *ToFormat
        #  (e.g. only banned_rights/admin_rights for ChatParticipant, etc.)
        # TODO: cache fetched values

        if values.poll_answers:
            selected_answers = await PollVote.filter(
                answer__poll__id__in=values.poll_answers, user__id=session.user_id,
            ).values_list("answer__poll__id", "answer__id")
            for poll_id, answer_id in selected_answers:
                if poll_id not in result.poll_answers:
                    result.poll_answers[poll_id] = set()
                result.poll_answers[poll_id].add(answer_id)

        peers_q = Q()

        if values.chat_participants or values.channel_participants:
            if values.chat_participants:
                peers_q |= Q(chat__id__in=values.chat_participants)
            if values.channel_participants:
                peers_q |= Q(channel__id__in=values.channel_participants)

            participants = await ChatParticipant.filter(peers_q, user__id=session.user_id)
            for participant in participants:
                if participant.chat_id is not None:
                    result.chat_participants[participant.chat_id] = participant
                else:
                    result.channel_participants[participant.channel_id] = participant

        if values.users:
            peers_q |= Q(user__id__in=values.users)

            contact_ids = set()
            for contact in await Contact.filter(
                Q(owner__id=session.user_id, target__id__in=values.users)
                | Q(owner__id__in=values.users, target__id=session.user_id)
            ):
                result.contacts[(contact.owner_id, contact.target_id)] = contact
                if contact.owner_id != session.user_id:
                    contact_ids.add(contact.owner_id)

            # NOTE (for future me refactoring this): this overwrites existing rules in context variables btw
            result.privacyrules = await PrivacyRule.has_access_to_bulk(
                users=values.users,
                user=session.user_id,
                keys=[
                    PrivacyRuleKeyType.PHONE_NUMBER,
                    PrivacyRuleKeyType.PROFILE_PHOTO,
                    PrivacyRuleKeyType.STATUS_TIMESTAMP,
                ],
                contacts=contact_ids,
            )

            for presence in await Presence.filter(user__id__in=values.users):
                result.presences[presence.user_id] = presence

        if peers_q.children:
            result.peers.update({
                (peer.type, peer.target_id_raw()): peer
                for peer in await Peer.filter(peers_q, owner__id=session.user_id)
            })

        if values.messages:
            # TODO: rewrite fetching user-specific fields
            messages = await MessageRef.filter(id__in=values.messages).select_related(*MessageRef.PREFETCH_FIELDS)
            for message in await MessageRef.to_tl_bulk(messages, session.user_id):
                result.dumb_messages[message.id] = message

        return result
