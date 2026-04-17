from __future__ import annotations

import asyncio
import struct
import time
from asyncio import Event
from io import BytesIO
from typing import TYPE_CHECKING

from loguru import logger
from lru import LRU
from mtproto import ConnectionRole
from mtproto.enums import TransportEvent
from mtproto.transport import Connection
from mtproto.transport.packets import MessagePacket, EncryptedMessagePacket, UnencryptedMessagePacket, \
    DecryptedMessagePacket, ErrorPacket, QuickAckPacket, BasePacket
from taskiq import AsyncTaskiqTask, TaskiqResult, TaskiqResultTimeoutError
from taskiq.brokers.inmemory_broker import InmemoryResultBackend
from taskiq.kicker import AsyncKicker

from piltover.auth_data import AuthData, GenAuthData
from piltover.exceptions import Disconnection, InvalidConstructorException, Unreachable
from piltover.gateway._keygen_handlers import KEYGEN_HANDLERS
from piltover.gateway._system_handlers import SYSTEM_HANDLERS
from piltover.session import Session, SessionManager
from piltover.tl import NewSessionCreated, BadServerSalt, BadMsgNotification, Long, Int, RpcError, ReqPq, ReqPqMulti, \
    MsgsAck
from piltover.tl.core_types import TLObject, MsgContainer, Message, RpcResult
from piltover.tl.functions.auth import BindTempAuthKey
from piltover.tl.functions.internal import CallRpc
from piltover.tl.types.internal import RpcResponse
from piltover.tl.utils import is_id_strictly_not_content_related, is_id_strictly_content_related
from piltover.utils.debug import measure_time

if TYPE_CHECKING:
    from .server import Gateway


_check_req_pq_tlid = (Int.write(ReqPq.tlid(), False), Int.write(ReqPqMulti.tlid(), False))


class Client:
    __slots__ = (
        "server", "reader", "writer", "conn", "peername", "gen_auth_data", "empty_session", "disconnect_timeout",
        "write_lock", "active_sessions", "active_keys", "message_available",
    )

    def __init__(self, server: Gateway, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        self.server = server

        self.reader = reader
        self.writer = writer
        self.conn = Connection(role=ConnectionRole.SERVER)
        self.peername: tuple[str, int] = writer.get_extra_info("peername")

        self.gen_auth_data: GenAuthData | None = None
        self.empty_session = Session(0)

        self.disconnect_timeout: asyncio.Timeout | None = None
        self.write_lock = asyncio.Lock()

        self.active_sessions = LRU(4, callback=self._session_evicted)
        self.active_keys = LRU(8)

        self.message_available = Event()

    @staticmethod
    def _session_evicted(_: ..., session: Session) -> None:
        session.disconnect()

    def _get_cached_session(self, auth_key_id: int, session_id: int) -> Session | None:
        uniq_id = (auth_key_id, session_id)
        if uniq_id in self.active_sessions:
            return self.active_sessions[uniq_id]

    def _get_session(self, session_id: int, auth_data: AuthData) -> tuple[Session, bool]:
        if (cached := self._get_cached_session(auth_data.auth_key_id, session_id)) is not None:
            return cached, False

        session, created = SessionManager.get_or_create(session_id, self, auth_data)
        session.connect(self)

        self.active_sessions[session.uniq_id()] = session
        return session, created

    async def read_packet(self) -> MessagePacket | None:
        packet = self.conn.next_event()
        if packet is TransportEvent.DISCONNECT:
            raise Disconnection
        if isinstance(packet, MessagePacket):
            return packet

        recv = await self.reader.read(32 * 1024)
        if not recv:
            raise Disconnection

        self.conn.data_received(recv)
        packet = self.conn.next_event()
        if packet is TransportEvent.DISCONNECT:
            raise Disconnection
        if not isinstance(packet, MessagePacket):
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

    async def _write_message(
            self, message_id: int, seq_no: int, data: bytes, session: Session,
    ) -> None:
        if not session.auth_data or session.auth_data.auth_key is None:
            raise Unreachable("Trying to send encrypted response, but auth_key is empty")

        logger.debug(f"Sending message {message_id} to {session.session_id}")

        session.update_salts_maybe(self.server.salt_key)

        decrypted = DecryptedMessagePacket(
            salt=session.salt_now.salt,
            session_id=session.session_id,
            message_id=message_id,
            seq_no=seq_no,
            data=data,
        )

        encrypted = decrypted.encrypt(session.auth_data.auth_key, ConnectionRole.SERVER)

        await self._write_packet(encrypted)

    async def send_unencrypted(self, obj: TLObject) -> None:
        logger.debug(obj)
        await self._write_packet(UnencryptedMessagePacket(
            self.empty_session.msg_id(in_reply=True),
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

    # TODO: move into Session?
    async def _is_message_bad(self, packet: DecryptedMessagePacket, session: Session, check_salt: bool) -> bool:
        # https://core.telegram.org/mtproto/service_messages_about_messages#notice-of-ignored-error-message

        error_code = 0
        inner_id = Int.read_bytes(packet.data[:4], False)

        if packet.message_id % 4 != 0:
            # 18: incorrect two lower order msg_id bits (the server expects client message msg_id to be divisible by 4)
            logger.debug(f"Client sent message id which is not divisible by 4")
            error_code = 18
        elif (packet.message_id >> 32) < (time.time() - 300):
            # 16: msg_id too low
            logger.debug(f"Client sent message id which is too low")
            error_code = 16
        elif (packet.message_id >> 32) > (time.time() + 30):
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
        # TODO: what's the difference between code 16 and code 20???
        # TODO: add validation for seq_no too low/high (code 32 and 33)

        if error_code:
            await session.enqueue(
                obj=BadMsgNotification(
                    bad_msg_id=packet.message_id,
                    bad_msg_seqno=packet.seq_no,
                    error_code=error_code,
                ),
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
            await session.enqueue(
                obj=BadServerSalt(
                    bad_msg_id=packet.message_id,
                    bad_msg_seqno=packet.seq_no,
                    error_code=48,
                    new_server_salt=Long.read_bytes(session.salt_now.salt),
                ),
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

            try:
                message = Message(
                    message_id=decrypted.message_id,
                    seq_no=decrypted.seq_no,
                    obj=TLObject.read(BytesIO(decrypted.data)),
                )
            except (struct.error, ValueError, InvalidConstructorException) as e:
                logger.opt(exception=e).error(f"Failed to read object. Raw data: {decrypted.data}")
                constructor = e.constructor if isinstance(e, InvalidConstructorException) else 0
                await session.enqueue(
                    RpcResult(
                        req_msg_id=decrypted.message_id,
                        result=RpcError(
                            error_code=400,
                            error_message=f"INPUT_METHOD_INVALID_{constructor}_0",
                        ),
                    ),
                    False,
                )
                return

            if not session.min_msg_id:
                session.min_msg_id = message.message_id
                await session.fetch_layer()
                logger.info(f"({self.peername}) Created session {session.session_id}")
                await session.enqueue(
                    obj=NewSessionCreated(
                        first_msg_id=message.message_id,
                        unique_id=session.session_id,
                        server_salt=Long.read_bytes(session.salt_now.salt),
                    ),
                    in_reply=False,
                )

            logger.debug(
                f"Received from {session.session_id} ({session.auth_data.auth_key_id} {session.user_id}): {message}"
            )
            asyncio.create_task(self.handle_encrypted_message(message, session))
        elif isinstance(packet, UnencryptedMessagePacket):
            decoded = TLObject.read(BytesIO(packet.message_data))
            if isinstance(decoded, (ReqPq, ReqPqMulti)):
                peeked = self.conn.peek_packet()
                if peeked is TransportEvent.DISCONNECT:
                    raise Disconnection
                packet: UnencryptedMessagePacket | None = None
                while isinstance(peeked, UnencryptedMessagePacket) and peeked.message_data[:4] in _check_req_pq_tlid:
                    logger.debug(f"Skipping reqPQ: {decoded}")
                    packet = self.conn.next_event()
                    peeked = self.conn.peek_packet()
                    if peeked is TransportEvent.DISCONNECT:
                        raise Disconnection
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

    async def _worker_loop_recv(self) -> None:
        while True:
            try:
                await self.recv()
            except Exception as e:
                logger.opt(exception=e).error("An error occurred in recv loop")
                raise

    async def _worker_loop_send(self) -> None:
        while True:
            try:
                await asyncio.wait_for(self.message_available.wait(), 0.1)
            except TimeoutError:
                pass

            sent = False
            for session in list(self.active_sessions.values()):
                if session.message_queue.empty():
                    continue
                message_id, seq_no, data = session.message_queue.get_nowait()
                await self._write_message(message_id, seq_no, data, session)
                sent = True

            if not sent and not any(not sess.message_queue.empty() for sess in self.active_sessions.values()):
                self.message_available.clear()

    @logger.catch
    async def worker(self):
        logger.debug(f"Client connected: {self.peername}")

        try:
            async with asyncio.timeout(None) as self.disconnect_timeout:
                await asyncio.gather(
                    self._worker_loop_recv(),
                    self._worker_loop_send(),
                )
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
                session.disconnect()

            self.active_sessions.clear()

    async def _wait_result_with_ack(
            self, task: AsyncTaskiqTask[str], message_id: int, session: Session, method_name: str,
    ) -> TaskiqResult[str]:
        start_time = time.perf_counter()

        try:
            return await task.wait_result(timeout=1.5)
        except TaskiqResultTimeoutError as e:
            logger.opt(exception=e).warning(f"Task timeout exceeded, sending ack to message {message_id}")
            await session.enqueue(MsgsAck(msg_ids=[message_id]), False)
            return await task.wait_result(timeout=15)
        finally:
            end_time = time.perf_counter()
            logger.debug(f"\"{method_name}\" ({message_id}) took {(end_time - start_time) * 1000:.2f} ms to execute")

    async def _process_request(self, request: Message, session: Session) -> RpcResult | None:
        if request.obj.tlid() in SYSTEM_HANDLERS:
            return await SYSTEM_HANDLERS[request.obj.tlid()](self, request, session)

        with measure_time("\"execute task\""):
            with measure_time("_kiq()"):
                task = await self._kiq(request.obj, session, request.message_id)
            with measure_time(".wait_result()"):
                try:
                    task_result = await self._wait_result_with_ack(
                        task, request.message_id, session, request.obj.__class__.__name__
                    )
                except Exception as e:
                    logger.opt(exception=e).error(f"Failed to get result for request {request!r}")
                    return RpcResult(
                        req_msg_id=request.message_id,
                        result=RpcError(error_code=500, error_message="INTERNAL_SERVER_ERROR_TIMEOUT"),
                    )

        if task_result.is_err:
            logger.opt(exception=task_result.error).error("An error occurred in worker while processing request.")
            return RpcResult(
                req_msg_id=request.message_id,
                result=RpcError(error_code=500, error_message="INTERNAL_SERVER_ERROR"),
            )

        result = task_result.return_value
        if not isinstance(self.server.broker.result_backend, InmemoryResultBackend):
            result = RpcResponse.read(BytesIO(bytes.fromhex(result)))
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
            await session.enqueue(result, True)
