import asyncio
import hashlib
import secrets
import time
from collections import defaultdict
from io import BytesIO
from typing import Callable, Awaitable, cast

import tgcrypto
from loguru import logger
from mtproto import Connection, ConnectionRole
from mtproto.packets import MessagePacket, EncryptedMessagePacket, UnencryptedMessagePacket, DecryptedMessagePacket, \
    ErrorPacket, QuickAckPacket, BasePacket

from piltover.auth_data import AuthData, GenAuthData
from piltover.context import RequestContext, request_ctx
from piltover.db.models.server_salt import ServerSalt
from piltover.exceptions import Disconnection, ErrorRpc, InvalidConstructorException
from piltover.session_manager import Session, SessionManager
from piltover.tl import TLObject, SerializationUtils, ResPQ, PQInnerData, ReqPqMulti, ReqPq, ReqDHParams, \
    SetClientDHParams, PQInnerDataDc, PQInnerDataTempDc, DhGenOk, Ping, NewSessionCreated, BadServerSalt, \
    BadMsgNotification, Long, Int
from piltover.tl.core_types import MsgContainer, Message, RpcResult
from piltover.tl.functions.auth import BindTempAuthKey
from piltover.tl.types import ServerDHInnerData, ServerDHParamsOk, ClientDHInnerData, RpcError, Pong, MsgsAck, \
    PQInnerDataTemp
from piltover.utils import generate_large_prime, gen_safe_prime, gen_keys, get_public_key_fingerprint, \
    load_private_key, load_public_key, background, Keys
from piltover.utils.rsa_utils import rsa_decrypt, rsa_pad_inverse


class MessageHandler:
    def __init__(self, name: str = None):
        self.name = name
        self.server: Server | None = None
        self.handlers: dict[
            int,
            Callable[[Client, Message, Session], Awaitable[TLObject | dict | None]],
        ] = {}

    def on_message(self, typ: type[TLObject]):
        def decorator(func: Callable[[Client, Message, Session], Awaitable[TLObject | dict | None]]):
            logger.trace(f"Added handler for function {typ.tlname()}" + (f" on {self.name}" if self.name else ""))

            self.handlers[typ.tlid()] = func
            return func

        return decorator


class Server:
    HOST = "0.0.0.0"
    PORT = 4430

    def __init__(self, host: str = HOST, port: int = PORT, server_keys: Keys | None = None):
        self.host = host
        self.port = port

        self.server_keys = server_keys
        if self.server_keys is None:
            self.server_keys = gen_keys()

        self.public_key = load_public_key(self.server_keys.public_key)
        self.private_key = load_private_key(self.server_keys.private_key)

        self.fingerprint: int = get_public_key_fingerprint(self.server_keys.public_key)

        self.clients: dict[str, Client] = {}
        self.handlers: dict[
            int,
            Callable[[Client, Message, Session], Awaitable[TLObject | bool | None]],
        ] = {}
        self.sys_handlers = defaultdict(list)

        self.salt_id = 0
        self.salt = b"\x00" * 8

    @logger.catch
    async def accept_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        client = Client(server=self, reader=reader, writer=writer)
        background(client.worker())

    async def serve(self):
        server = await asyncio.start_server(self.accept_client, self.host, self.port)
        async with server:
            await server.serve_forever()

    async def register_auth_key(self, auth_key_id: int, auth_key: bytes, expires_in: int | None):
        for handler in self.sys_handlers["auth_key_set"]:
            await handler(auth_key_id, auth_key, expires_in)

    async def get_auth_key(self, auth_key_id: int) -> tuple[int, bytes, bool] | None:
        for handler in self.sys_handlers["auth_key_get"]:
            if (auth_key_info := await handler(auth_key_id)) is not None:
                return auth_key_info

    def on_message(self, typ: type[TLObject]):
        def decorator(func: Callable[[Client, Message, Session], Awaitable[TLObject | bool | None]]):
            logger.debug(f"Added handler for function {typ!r}")

            self.handlers[typ.tlid()] = func
            return func

        return decorator

    def register_handler(self, handler: MessageHandler) -> None:
        if handler.server is not None:
            raise RuntimeError(f"Handler {handler} already registered!")
        self.handlers.update(handler.handlers)

        handler.server = self

    def on_auth_key_set(self, func: Callable[[int, bytes, int | None], Awaitable[None]]):
        self.sys_handlers["auth_key_set"].append(func)
        return func

    def on_auth_key_get(self, func: Callable[[int], Awaitable[tuple[int, bytes, bool] | None]]):
        self.sys_handlers["auth_key_get"].append(func)
        return func

    async def get_current_salt(self) -> bytes:
        current_id = int(time.time() // (60 * 60))
        if self.salt_id != current_id:
            logger.debug("Current salt is expired, fetching new one")
            salt, _ = await ServerSalt.get_or_create(id=current_id)
            self.salt_id = salt.id
            self.salt = Long.write(salt.salt)

        return self.salt


class Client:
    __slots__ = (
        "server", "reader", "writer", "conn", "peername", "auth_data", "empty_session", "session", "no_updates",
        "layer",
    )

    def __init__(self, server: Server, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        self.server: Server = server

        self.reader = reader
        self.writer = writer
        self.conn = Connection(role=ConnectionRole.SERVER)
        self.peername: tuple[str, int] = writer.get_extra_info("peername")

        self.auth_data: AuthData | None = None
        self.empty_session = Session(self, 0)
        self.session: Session | None = None

        self.no_updates = False
        self.layer = 177

    def _get_session(self, session_id: int) -> tuple[Session, bool]:
        if self.session is not None:
            if self.session.session_id == session_id:
                return self.session, False
            self.session.cleanup()

        self.session, created = SessionManager.get_or_create(self, session_id)
        if not created and self.session.online:
            self.session.cleanup()
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
            return

        return packet

    async def _write(self, packet: BasePacket) -> None:
        to_send = self.conn.send(packet)
        self.writer.write(to_send)
        await self.writer.drain()

    async def _send_raw(self, message: Message, session: Session) -> None:
        if not self.auth_data or self.auth_data.auth_key is None or self.auth_data.auth_key_id is None:
            logger.warning("Trying to send encrypted response, but auth_key is empty")
            raise Disconnection(404)

        logger.debug(f"Sending to {self.session.session_id if self.session else 0}: {message}")

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

    async def handle_unencrypted_message(self, obj: TLObject):
        if isinstance(obj, (ReqPqMulti, ReqPq)):
            req_pq_multi = obj
            p = generate_large_prime(31)
            q = generate_large_prime(31)

            if p > q:
                p, q = q, p

            self.auth_data = GenAuthData()
            self.auth_data.p, self.auth_data.q = p, q

            if p == -1 or q == -1 or q == p:
                raise Disconnection(404)

            pq = self.auth_data.p * self.auth_data.q

            self.auth_data.server_nonce = int.from_bytes(secrets.token_bytes(128 // 8), byteorder="big")

            await self.send_unencrypted(ResPQ(
                nonce=req_pq_multi.nonce,
                server_nonce=self.auth_data.server_nonce,
                pq=pq.to_bytes(64 // 8, "big"),
                server_public_key_fingerprints=[self.server.fingerprint]
            ))
        elif isinstance(obj, ReqDHParams):
            if not self.auth_data:
                raise Disconnection(404)

            req_dh_params = obj

            if len(req_dh_params.p) != 4 or len(req_dh_params.q) != 4:
                raise Disconnection(404)
            client_p = int.from_bytes(req_dh_params.p, "big", signed=False)
            client_q = int.from_bytes(req_dh_params.q, "big", signed=False)
            if client_p != self.auth_data.p or client_q != self.auth_data.q:
                raise Disconnection(404)

            if self.auth_data.server_nonce != req_dh_params.server_nonce:
                raise Disconnection(404)

            encrypted_data: bytes = req_dh_params.encrypted_data
            if len(encrypted_data) != 256:
                raise Disconnection(404)

            old = False
            key_aes_encrypted = rsa_decrypt(encrypted_data, self.server.public_key, self.server.private_key)
            try:
                key_aes_encrypted = rsa_pad_inverse(key_aes_encrypted)
            except RuntimeError as e:
                logger.debug(f"rsa_pad_inverse raised error: {e}. Using old pre-RSA_PAD encryption.")
                old = True
            key_aes_encrypted = key_aes_encrypted.lstrip(b"\0")

            # TODO: assert key_aes_encrypted < public.n, "key_aes_encrypted greater than RSA modulus, aborting..."

            if old:
                p_q_inner_data = PQInnerData.read(BytesIO(key_aes_encrypted[20:]))

                digest = key_aes_encrypted[:20]
                if hashlib.sha1(p_q_inner_data.write()).digest() != digest:
                    logger.debug("sha1 of data doesn't match")
                    raise Disconnection(404)
            else:
                p_q_inner_data = PQInnerData.read(BytesIO(key_aes_encrypted))

            logger.debug(f"p_q_inner_data: {p_q_inner_data}")

            if not isinstance(p_q_inner_data, (PQInnerData, PQInnerDataDc, PQInnerDataTemp, PQInnerDataTempDc)):
                logger.debug(f"Expected p_q_inner_data_*, got instead {type(p_q_inner_data)}")
                raise Disconnection(404)

            if self.auth_data.server_nonce != p_q_inner_data.server_nonce:
                raise Disconnection(404)

            self.auth_data.is_temp = isinstance(p_q_inner_data, (PQInnerDataTemp, PQInnerDataTempDc))
            self.auth_data.expires_in = max(cast(PQInnerDataTempDc, p_q_inner_data).expires_in, 86400) \
                if self.auth_data.is_temp else 0

            new_nonce = p_q_inner_data.new_nonce.to_bytes(256 // 8, "little", signed=False)
            self.auth_data.new_nonce = new_nonce
            # TODO: set server salt to server_nonce

            logger.info("Generating safe prime...")
            self.auth_data.dh_prime, g = gen_safe_prime(2048)

            logger.info("Prime successfully generated")

            self.auth_data.a = int.from_bytes(secrets.token_bytes(256), "big")
            g_a = pow(g, self.auth_data.a, self.auth_data.dh_prime)

            if g <= 1 or g >= self.auth_data.dh_prime - 1 \
                    or g_a <= 1 or g_a >= self.auth_data.dh_prime - 1 \
                    or g_a <= 2 ** (2048 - 64) or g_a >= self.auth_data.dh_prime - 2 ** (2048 - 64):
                raise Disconnection(404)

            answer = ServerDHInnerData(
                nonce=p_q_inner_data.nonce,
                server_nonce=self.auth_data.server_nonce,
                g=g,
                dh_prime=self.auth_data.dh_prime.to_bytes(2048 // 8, "big", signed=False),
                g_a=g_a.to_bytes(256, "big"),
                server_time=int(time.time()),
            ).write()

            self.auth_data.server_nonce_bytes = server_nonce_bytes = self.auth_data.server_nonce.to_bytes(
                128 // 8, "little", signed=False
            )

            answer_with_hash = hashlib.sha1(answer).digest() + answer
            answer_with_hash += secrets.token_bytes(-len(answer_with_hash) % 16)
            self.auth_data.tmp_aes_key = (
                    hashlib.sha1(new_nonce + server_nonce_bytes).digest()
                    + hashlib.sha1(server_nonce_bytes + new_nonce).digest()[:12]
            )
            self.auth_data.tmp_aes_iv = (
                    hashlib.sha1(server_nonce_bytes + new_nonce).digest()[12:]
                    + hashlib.sha1(new_nonce + new_nonce).digest()
                    + new_nonce[:4]
            )
            encrypted_answer = tgcrypto.ige256_encrypt(
                answer_with_hash,
                self.auth_data.tmp_aes_key,
                self.auth_data.tmp_aes_iv,
            )

            await self.send_unencrypted(ServerDHParamsOk(
                nonce=p_q_inner_data.nonce,
                server_nonce=self.auth_data.server_nonce,
                encrypted_answer=encrypted_answer,
            ))
        elif isinstance(obj, SetClientDHParams):
            if self.auth_data is None \
                    or self.auth_data.tmp_aes_key is None \
                    or self.auth_data.server_nonce != obj.server_nonce:
                raise Disconnection(404)

            set_client_DH_params = obj
            decrypted_params = tgcrypto.ige256_decrypt(
                set_client_DH_params.encrypted_data,
                self.auth_data.tmp_aes_key,
                self.auth_data.tmp_aes_iv,
            )
            client_DH_inner_data = ClientDHInnerData.read(BytesIO(decrypted_params[20:]))
            if hashlib.sha1(client_DH_inner_data.write()).digest() != decrypted_params[:20]:
                logger.debug("sha1 hash mismatch for client_DH_inner_data")
                raise Disconnection(404)

            if self.auth_data.server_nonce != client_DH_inner_data.server_nonce:
                raise Disconnection(404)

            self.auth_data.auth_key = auth_key = pow(
                int.from_bytes(client_DH_inner_data.g_b, "big"),
                self.auth_data.a,
                self.auth_data.dh_prime,
            ).to_bytes(256, "big")

            auth_key_digest = hashlib.sha1(auth_key).digest()
            auth_key_hash = auth_key_digest[-8:]
            auth_key_aux_hash = auth_key_digest[:8]

            await self.send_unencrypted(DhGenOk(
                nonce=client_DH_inner_data.nonce,
                server_nonce=self.auth_data.server_nonce,
                new_nonce_hash1=int.from_bytes(
                    hashlib.sha1(self.auth_data.new_nonce + bytes([1]) + auth_key_aux_hash).digest()[-16:], "little"
                )
            ))

            self.auth_data.auth_key_id = Int.read_bytes(auth_key_hash)
            await self.server.register_auth_key(
                auth_key_id=self.auth_data.auth_key_id,
                auth_key=self.auth_data.auth_key,
                expires_in=self.auth_data.expires_in,
            )
            logger.info("Auth key generation successfully completed!")
        elif isinstance(obj, MsgsAck):
            return
        else:
            logger.debug(f"Received unexpected unencrypted message: {obj}")
            raise Disconnection(404)

    async def handle_encrypted_message(self, req_message: Message, session_id: int):
        sess, created = self._get_session(session_id)
        sess.update_incoming_content_related_msgs(req_message.obj, req_message.seq_no)

        if created:
            logger.info(f"({self.peername}) Created session {session_id}")
            await self.send(
                NewSessionCreated(
                    first_msg_id=req_message.message_id,
                    unique_id=sess.session_id,
                    server_salt=Long.read_bytes(await self.server.get_current_salt()),
                ),
                sess,
            )

        if isinstance(req_message.obj, MsgContainer):
            results = []
            for msg in req_message.obj.messages:
                result = await self.propagate(msg, sess)
                if result is None:
                    continue
                results.append((result, msg))

            if not results:
                logger.warning("Empty msg_container, returning...")
                return

            return await self.send_container(results, sess)

        if (result := await self.propagate(req_message, sess)) is None:
            return

        await self.send(result, sess, originating_request=req_message)

    # https://core.telegram.org/mtproto/service_messages_about_messages#notice-of-ignored-error-message
    async def _is_message_bad(self, packet: DecryptedMessagePacket, check_salt: bool) -> bool:
        error_code = 0

        if packet.message_id % 4 != 0:
            # 18: incorrect two lower order msg_id bits (the server expects client message msg_id to be divisible by 4)
            logger.debug(f"Client sent message id which is not divisible by 4")
            error_code = 18
        elif (packet.message_id >> 32) < (time.time() - 300):
            # 16: msg_id too low
            logger.debug(f"Client sent message id which is too low")
            error_code = 16
        elif (packet.message_id >> 32) < (time.time() - 300):
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
                Session(self, packet.session_id),
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
                Session(self, packet.session_id),
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
            if await self._is_message_bad(decrypted, decrypted.data[:4] != Int.write(BindTempAuthKey.tlid())):
                return

            message = Message(
                message_id=decrypted.message_id,
                seq_no=decrypted.seq_no,
                obj=TLObject.read(BytesIO(decrypted.data)),
            )
            request_ctx.set(RequestContext(
                packet.auth_key_id, decrypted.message_id, decrypted.session_id, message.obj, self
            ))

            logger.debug(f"Received from {self.session.session_id if self.session else 0}: {message}")
            await self.handle_encrypted_message(message, decrypted.session_id)
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

    async def decrypt_noreplace(self, message: EncryptedMessagePacket, v1: bool = False) -> DecryptedMessagePacket:
        auth_data_bak = self.auth_data
        try:
            result = await self.decrypt(message, v1)
            self.auth_data = auth_data_bak
            return result
        except:
            self.auth_data = auth_data_bak
            raise

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
            await self._worker_loop()
        except Disconnection as err:
            if err.transport_error is not None:
                await self._write(ErrorPacket(err.transport_error))

            self.writer.close()
            await self.writer.wait_closed()

            logger.info("Client disconnected")

        if self.session is not None:
            logger.info(f"Session {self.session.session_id} removed")
            self.session.cleanup()

    async def propagate(self, request: Message, session: Session) -> TLObject | RpcResult | None:
        handler = self.server.handlers.get(request.obj.tlid())
        if handler is None:
            logger.warning(f"No handler found for obj: {request.obj}")
            return RpcResult(
                req_msg_id=request.message_id,
                result=RpcError(error_code=500, error_message="Not implemented"),
            )

        request_obj = request.obj if isinstance(request, Message) else request
        RequestContext.save(obj=request_obj)

        try:
            result = await handler(self, request, session)
        except ErrorRpc as e:
            result = RpcError(error_code=e.error_code, error_message=e.error_message)
        except InvalidConstructorException:
            raise
        except Exception as e:
            logger.warning(e)
            result = RpcError(error_code=500, error_message="Server error")

        RequestContext.restore()

        if result is None:
            logger.warning(f"Handler for function {request_obj} returned None!")
            result = RpcError(error_code=500, error_message="Server error")
        elif result is False:
            return

        if isinstance(result, (Ping, Pong, RpcResult)):
            return result

        return RpcResult(req_msg_id=request.message_id, result=result)
