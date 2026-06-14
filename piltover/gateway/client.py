from __future__ import annotations

import asyncio
import struct
import time
from asyncio import Event
from io import BytesIO
from typing import TYPE_CHECKING, cast, Any

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
from piltover.tl import NewSessionCreated, Long, Int, RpcError, ReqPq, ReqPqMulti, MsgsAck
from piltover.tl.core_types import TLObject, MsgContainer, Message, RpcResult
from piltover.tl.functions.auth import BindTempAuthKey
from piltover.tl.functions.internal import CallRpc
from piltover.tl.types.internal import RpcResponse
from piltover.utils.debug import measure_time
from ..db.models import AuthKey

if TYPE_CHECKING:
    from .server import Gateway


_check_req_pq_tlid = (
    Int.write(ReqPq.tlid(), False),
    Int.write(ReqPqMulti.tlid(), False),
)


class Client(asyncio.Protocol):
    __slots__ = (
        "server", "conn", "peername", "gen_auth_data", "empty_session", "disconnect_timeout_handle",
        "process_lock", "active_sessions", "active_keys", "message_available", "loop", "tasks", "transport",
    )

    def __init__(self, server: Gateway):
        t0 = time.perf_counter()

        self.server = server

        self.transport: asyncio.BaseTransport | None = None
        self.conn = Connection(role=ConnectionRole.SERVER)
        self.peername: tuple[str, int] | None = None

        self.gen_auth_data: GenAuthData | None = None
        self.empty_session = Session(0)

        self.disconnect_timeout_handle: asyncio.TimerHandle | None = None
        self.process_lock = asyncio.Lock()

        self.active_sessions = LRU(4, callback=self._session_evicted)
        self.active_keys = cast("LRU[int, bytes]", LRU(8))

        self.message_available = Event()
        self.loop = asyncio.get_running_loop()
        self.tasks = set()

        dt = time.perf_counter() - t0
        print("init", dt)

    def connection_made(self, transport: asyncio.BaseTransport) -> None:
        self.transport = transport
        self.peername = transport.get_extra_info("peername")
        logger.info("Client connected: {addr}", addr=self.peername)

        task = self.loop.create_task(self._worker_loop_send())
        task.add_done_callback(self.send_loop_done)
        self.tasks.add(task)

    def data_received(self, data: bytes) -> None:
        self.conn.data_received(data)
        if not self.conn.has_packet():
            return
        if self.conn.peek_packet() is TransportEvent.DISCONNECT:
            self.close_transport()
            return

        task = self.loop.create_task(self._process_received())
        task.add_done_callback(self.tasks.discard)
        self.tasks.add(task)

    def connection_lost(self, exc: BaseException) -> None:
        self.transport = None

        logger.info("Client disconnected: {addr}", addr=self.peername)

        for session in self.active_sessions.values():
            logger.info(f"Session {session.session_id} removed")
            session.disconnect()

        self.active_sessions.clear()

    def close_transport(self) -> None:
        if self.transport is not None:
            self.transport.close()

    def timeout_disconnect(self) -> None:
        logger.debug("Client disconnected because of expired timeout")
        self.close_transport()

    def send_loop_done(self, task: asyncio.Task) -> None:
        logger.debug("Send loop stopped, disconnecting")
        self.tasks.discard(task)
        self.close_transport()

    async def _process_received(self) -> None:
        async with self.process_lock:
            await self._process_received_locked()

    async def _process_received_locked(self) -> None:
        while self.conn.has_packet():
            packet = self.conn.next_event()
            if packet is TransportEvent.DISCONNECT or self.transport is None:
                self.close_transport()
                return

            if not isinstance(packet, MessagePacket):
                await asyncio.sleep(0)
                continue

            try:
                await self._process_packet(packet)
            except Disconnection as err:
                if err.transport_error is not None:
                    await self._write_packet(ErrorPacket(err.transport_error), ignore_errors=True)
                self.close_transport()
            except Exception as e:
                logger.opt(exception=e).error("Error occurred while processing packet")
                self.close_transport()

    @staticmethod
    def _session_evicted(_: Any, session: Session) -> None:
        session.disconnect()

    def _get_cached_session(self, auth_key_id: int, session_id: int) -> Session | None:
        uniq_id = (auth_key_id, session_id)
        return self.active_sessions.get(uniq_id, None)

    def _get_session(self, session_id: int, auth_data: AuthData) -> tuple[Session, bool]:
        if (cached := self._get_cached_session(auth_data.auth_key_id, session_id)) is not None:
            return cached, False

        session, created = SessionManager.get_or_create(session_id, self, auth_data)
        session.connect(self)

        self.active_sessions[session.uniq_id()] = session
        return session, created

    async def _process_packet(self, packet: MessagePacket) -> None:
        if isinstance(packet, EncryptedMessagePacket):
            auth_data = None
            if packet.auth_key_id in self.active_keys:
                auth_key = self.active_keys[packet.auth_key_id]
            else:
                auth_data = await self._get_auth_data(packet.auth_key_id)
                self.active_keys[packet.auth_key_id] = auth_key = cast(bytes, auth_data.auth_key)

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
            if await session.is_message_bad(decrypted, check_salt):
                return

            try:
                message = Message(
                    message_id=decrypted.message_id,
                    seq_no=decrypted.seq_no,
                    obj=TLObject.read(BytesIO(decrypted.data)),
                )
            except (struct.error, ValueError, InvalidConstructorException) as e:
                logger.opt(exception=e).error("Failed to read object. Raw data: {raw_data}", raw_data=decrypted.data)
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
                "Received from {session_id} ({auth_key_id} {user_id}): {message}",
                session_id=session.session_id,
                auth_key_id=session.auth_data.auth_key_id,
                user_id=session.user_id,
                message=message,
            )
            task = self.loop.create_task(self.handle_encrypted_message(message, session))
            self.tasks.add(task)
            task.add_done_callback(self.tasks.discard)
        elif isinstance(packet, UnencryptedMessagePacket):
            decoded = TLObject.read(BytesIO(packet.message_data))
            if isinstance(decoded, (ReqPq, ReqPqMulti)):
                peeked = self.conn.peek_packet()
                if peeked is TransportEvent.DISCONNECT:
                    raise Disconnection
                packet: UnencryptedMessagePacket | None = None
                while isinstance(peeked, UnencryptedMessagePacket) and peeked.message_data[:4] in _check_req_pq_tlid:
                    logger.debug("Skipping reqPQ: {req_pq}", req_pq=decoded)
                    packet = cast(UnencryptedMessagePacket, self.conn.next_event())
                    peeked = self.conn.peek_packet()
                    if peeked is TransportEvent.DISCONNECT:
                        raise Disconnection
                    await asyncio.sleep(0)

                if packet is not None:
                    decoded = TLObject.read(BytesIO(packet.message_data))

            logger.debug("{decoded}", decoded=decoded)
            await self.handle_unencrypted_message(decoded)

    async def _write_packet(self, packet: BasePacket, ignore_errors: bool = False) -> None:
        to_send = self.conn.send(packet)
        try:
            self.transport.write(to_send)
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
        with measure_time("session.refresh_auth_maybe()"):
            await session.refresh_auth_maybe()

        if isinstance(req_message.obj, MsgContainer):
            await asyncio.gather(*[
                self.propagate(msg, session)
                for msg in req_message.obj.messages
            ])
        else:
            await self.propagate(req_message, session)

    async def _get_auth_data(self, auth_key_id: int) -> AuthData:
        logger.debug("Requested auth key: {auth_key_id}", auth_key_id=auth_key_id)
        data = await AuthKey.get_auth_data(auth_key_id)
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
            logger.debug(
                "\"{method_name}\" ({message_id}) took {time_taken:.2f} ms to execute",
                method_name=method_name,
                message_id=message_id,
                time_taken=(end_time - start_time) * 1000,
            )

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
            await session.fetch_layer()

        return result.obj

    async def propagate(self, request: Message, session: Session) -> RpcResult | None:
        if (result := await self._process_request(request, session)) is not None:
            await session.enqueue(result, True)
