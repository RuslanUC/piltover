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
    ErrorPacket

from piltover.auth_data import AuthData, GenAuthData
from piltover.context import RequestContext, request_ctx
from piltover.exceptions import Disconnection, ErrorRpc, InvalidConstructorException
from piltover.session_manager import Session, SessionManager
from piltover.tl import TLObject, SerializationUtils, ResPQ, Long, PQInnerData, ReqPqMulti, ReqPq, ReqDHParams, \
    SetClientDHParams, PQInnerDataDc, PQInnerDataTempDc, DhGenOk, Ping, NewSessionCreated
from piltover.tl.core_types import MsgContainer, Message, RpcResult
from piltover.tl.types import ServerDHInnerData, ServerDHParamsOk, ClientDHInnerData, RpcError, Pong, MsgsAck
from piltover.tl.utils import is_content_related
from piltover.types import Keys
from piltover.utils import read_int, generate_large_prime, gen_safe_prime, gen_keys, get_public_key_fingerprint, \
    load_private_key, load_public_key, background
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
            logger.debug("Added handler for function {typ!r}" + (f" on {self.name}" if self.name else ""),
                         typ=typ.tlname())

            self.handlers[typ.tlid()] = func
            return func

        return decorator


class Server:
    HOST = "0.0.0.0"
    PORT = 4430

    def __init__(
            self,
            host: str | None = None,
            port: int | None = None,
            server_keys: Keys | None = None,
    ):
        self.host = host if host is not None else self.HOST
        self.port = port if port is not None else self.PORT

        self.server_keys = server_keys
        if self.server_keys is None:
            self.server_keys = gen_keys()

        self.public_key = load_public_key(self.server_keys.public_key)
        self.private_key = load_private_key(self.server_keys.private_key)

        self.fingerprint: int = get_public_key_fingerprint(self.server_keys.public_key)

        self.clients: dict[str, Client] = {}
        self.handlers: dict[
            int,
            Callable[[Client, Message, Session], Awaitable[TLObject | dict | None]],
        ] = {}
        self.sys_handlers = defaultdict(list)
        self.salt: int = 0

    @logger.catch
    async def accept_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        client = Client(server=self, reader=reader, writer=writer)
        background(client.worker())

    async def serve(self):
        #aiomonitor.start_monitor(get_event_loop(), port=0, console_port=0, webui_port=50080)
        server = await asyncio.start_server(self.accept_client, self.HOST, self.PORT)
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
            logger.debug("Added handler for function {typ!r}", typ=typ)

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


class Client:
    def __init__(self, server: Server, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        self.server: Server = server

        self.reader = reader
        self.writer = writer
        self.conn = Connection(role=ConnectionRole.SERVER)
        self.peername: tuple[str, int] = writer.get_extra_info("peername")

        self.auth_data: AuthData | None = None
        self.empty_session = Session(self, 0)

        self.no_updates = False

    async def internal_updates_handler(self) -> None:
        ...

    async def read_message(self) -> MessagePacket | None:
        packet = self.conn.receive(b"")
        if isinstance(packet, MessagePacket):
            return packet

        recv = await self.reader.read(32 * 1024)
        if not recv:
            raise Disconnection
        packet = self.conn.receive(recv)
        if not isinstance(packet, MessagePacket):
            return
        return packet

    async def _send_raw(self, message: Message, session: Session) -> None:
        assert self.auth_data.auth_key is not None, "FATAL: self.auth_key is None"
        assert self.auth_data.auth_key_id is not None, "FATAL: self.auth_key_id is None"

        encrypted = DecryptedMessagePacket(
            salt=Long.write(self.server.salt),
            session_id=session.session_id,
            message_id=message.message_id,
            seq_no=message.seq_no,
            data=message.obj.write(),
        ).encrypt(self.auth_data.auth_key, ConnectionRole.SERVER)

        to_send = self.conn.send(encrypted)
        self.writer.write(to_send)
        await self.writer.drain()

    async def send(
            self, obj: TLObject, session: Session,  originating_request: Message | None = None,
    ):
        logger.debug(f"Sending: {obj}")
        message = self._pack_message(session, obj, originating_request)

        await self._send_raw(message, session)

    async def send_container(self, objects: list[tuple[TLObject, Message]], session: Session):
        logger.debug(f"Sending: {objects}")
        message = self._pack_container(session, objects)

        await self._send_raw(message, session)

    async def send_unencrypted(self, obj: TLObject) -> None:
        logger.debug(obj)
        to_send = self.conn.send(UnencryptedMessagePacket(
            self.empty_session.msg_id(in_reply=True),
            obj.write(),
        ))
        self.writer.write(to_send)
        await self.writer.drain()

    async def handle_unencrypted_message(self, obj: TLObject):
        if isinstance(obj, (ReqPqMulti, ReqPq)):
            req_pq_multi = obj
            p = generate_large_prime(31)
            q = generate_large_prime(31)

            if p > q:
                p, q = q, p

            self.auth_data = GenAuthData()
            self.auth_data.p, self.auth_data.q = p, q

            assert p != -1, "p is -1"
            assert q != -1, "q is -1"
            assert p != q

            pq = self.auth_data.p * self.auth_data.q

            self.auth_data.server_nonce = int.from_bytes(secrets.token_bytes(128 // 8), byteorder="big")

            await self.send_unencrypted(ResPQ(
                nonce=req_pq_multi.nonce,
                server_nonce=self.auth_data.server_nonce,
                pq=pq.to_bytes(64 // 8, "big"),
                server_public_key_fingerprints=[self.server.fingerprint]
            ))
        elif isinstance(obj, ReqDHParams):
            assert self.auth_data

            req_dh_params = obj

            if len(req_dh_params.p) != 4 or len(req_dh_params.q) != 4:
                raise Disconnection(404)
            client_p = int.from_bytes(req_dh_params.p, "big", signed=False)
            client_q = int.from_bytes(req_dh_params.q, "big", signed=False)
            if client_p != self.auth_data.p or client_q != self.auth_data.q:
                raise Disconnection(404)

            # TODO: check server_nonce in other places too
            if self.auth_data.server_nonce != req_dh_params.server_nonce:
                raise Disconnection(404)

            encrypted_data: bytes = req_dh_params.encrypted_data
            if len(encrypted_data) != 256:
                raise Disconnection(404)

            old = False
            key_aes_encrypted = rsa_decrypt(encrypted_data, self.server.public_key, self.server.private_key)
            try:
                key_aes_encrypted = rsa_pad_inverse(key_aes_encrypted)
            except AssertionError as e:
                logger.debug(f"rsa_pad_inverse raised error: {e}. Using old pre-RSA_PAD encryption.")
                old = True
            key_aes_encrypted = key_aes_encrypted.lstrip(b"\0")

            # TODO: restart generation with dh_fail instead?
            # assert key_aes_encrypted >= public.n, "key_aes_encrypted greater than RSA modulus, aborting..."

            if old:
                p_q_inner_data = PQInnerData.read(BytesIO(key_aes_encrypted[20:]))

                digest = key_aes_encrypted[:20]
                assert hashlib.sha1(p_q_inner_data.write()).digest() == digest, "sha1 of data doesn't match"
            else:
                p_q_inner_data = PQInnerData.read(BytesIO(key_aes_encrypted))

            logger.debug(f"p_q_inner_data: {p_q_inner_data}")

            assert isinstance(p_q_inner_data, (PQInnerData, PQInnerDataDc, PQInnerDataTempDc)), \
                f"Expected p_q_inner_data_*, got instead {type(p_q_inner_data)}"

            self.auth_data.is_temp = isinstance(p_q_inner_data, PQInnerDataTempDc)
            self.auth_data.expires_in = max(cast(PQInnerDataTempDc, p_q_inner_data).expires_in, 86400) \
                if self.auth_data.is_temp else 0

            new_nonce: bytes = p_q_inner_data.new_nonce.to_bytes(256 // 8, "little", signed=False)
            self.auth_data.new_nonce = new_nonce

            logger.info("Generating safe prime...")
            self.auth_data.dh_prime, g = gen_safe_prime(2048)

            logger.info("Prime successfully generated")

            self.auth_data.a = int.from_bytes(secrets.token_bytes(256), "big")
            g_a = pow(g, self.auth_data.a, self.auth_data.dh_prime).to_bytes(256, "big")

            # https://core.telegram.org/mtproto/auth_key#dh-key-exchange-complete
            # IMPORTANT: Apart from the conditions on the Diffie-Hellman
            # prime dh_prime and generator g, both sides are to check
            # that g, g_a and g_b are greater than 1 and less than dh_prime - 1.
            # We recommend checking that g_a and g_b are between 2^{2048-64} and dh_prime - 2^{2048-64} as well.
            # TODO

            answer = ServerDHInnerData(
                nonce=p_q_inner_data.nonce,
                server_nonce=self.auth_data.server_nonce,
                g=g,
                dh_prime=self.auth_data.dh_prime.to_bytes(2048 // 8, "big", signed=False),
                g_a=g_a,
                server_time=int(time.time()),
            )
            answer = answer.write()

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
                server_nonce=p_q_inner_data.server_nonce,
                encrypted_answer=encrypted_answer,
            ))
        elif isinstance(obj, SetClientDHParams):
            if self.auth_data is None or self.auth_data.tmp_aes_key is None:
                raise Disconnection(404)
            set_client_DH_params = obj
            decrypted_params = tgcrypto.ige256_decrypt(
                set_client_DH_params.encrypted_data,
                self.auth_data.tmp_aes_key,
                self.auth_data.tmp_aes_iv,
            )
            client_DH_inner_data = ClientDHInnerData.read(BytesIO(decrypted_params[20:]))
            assert hashlib.sha1(client_DH_inner_data.write()).digest() == decrypted_params[:20], \
                "sha1 hash mismatch for client_DH_inner_data"

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

            self.auth_data.auth_key_id = read_int(auth_key_hash)
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
        sess, created = SessionManager().get_or_create(self, session_id)
        sess.update_incoming_content_related_msgs(req_message.obj, req_message.seq_no)

        if created:
            logger.info(f"({self.peername}) Created session {session_id}")
            await self.send(
                NewSessionCreated(first_msg_id=req_message.message_id, unique_id=sess.session_id, server_salt=0),
                sess
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

    async def recv(self):
        message = await self.read_message()
        if isinstance(message, EncryptedMessagePacket):
            decrypted = await self.decrypt(message)
            payload = Message(
                message_id=decrypted.message_id,
                seq_no=decrypted.seq_no,
                obj=TLObject.read(BytesIO(decrypted.data)),
            )
            request_ctx.set(RequestContext(
                message.auth_key_id, decrypted.message_id, decrypted.session_id, payload.obj, self
            ))

            logger.debug(payload)
            await self.handle_encrypted_message(payload, decrypted.session_id)
        elif isinstance(message, UnencryptedMessagePacket):
            decoded = SerializationUtils.read(BytesIO(message.message_data), TLObject)
            logger.debug(decoded)
            await self.handle_unencrypted_message(decoded)

    # TODO: move to session?
    # https://core.telegram.org/mtproto/description#message-identifier-msg-id
    @staticmethod
    def _pack_message(
            session: Session, obj: TLObject, originating_request: Message | None = None
    ) -> Message:
        if originating_request is None:
            msg_id = session.msg_id(in_reply=False)
        else:
            if is_content_related(obj):
                msg_id = session.msg_id(in_reply=True)
            else:
                msg_id = originating_request.message_id + 1

        message = Message(message_id=msg_id, seq_no=session.get_outgoing_seq_no(obj), obj=obj)
        logger.trace(f"Actually sending: {message}")

        return message

    # TODO: move to session?
    # https://core.telegram.org/mtproto/description#message-identifier-msg-id
    def _pack_container(self, session: Session, objects: list[tuple[TLObject, Message]]) -> Message:
        container = MsgContainer(messages=[])
        for obj, originating_request in objects:
            if is_content_related(obj):
                msg_id = session.msg_id(in_reply=True)
            else:
                msg_id = originating_request.message_id + 1
            seq_no = session.get_outgoing_seq_no(obj)

            container.messages.append(Message(message_id=msg_id, seq_no=seq_no, obj=obj))

        logger.trace(f"Actually sending: {container}")

        return self._pack_message(session, container)

    async def decrypt(self, message: EncryptedMessagePacket, v1: bool = False) -> DecryptedMessagePacket:
        if self.auth_data is None or not self.auth_data.check_key(message.auth_key_id):
            got = await self.server.get_auth_key(message.auth_key_id)
            if got is None:
                logger.info(f"Client ({self.peername}) sent unknown auth_key_id {message.auth_key_id}, disconnecting with 404")
                raise Disconnection(404)
            self.auth_data = AuthData(*got)

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

    @logger.catch
    async def worker(self):
        logger.debug(f"Client connected: {self.peername}")

        try:
            while True:
                try:
                    await self.recv()
                except AssertionError:
                    logger.exception("Unexpected failed assertion", backtrace=True)
                except InvalidConstructorException as e:
                    if e.wrong_type:
                        continue
                    logger.error(f"Invalid constructor: {e.constructor} ({hex(e.constructor)[2:]})" +
                                 ("" if not e.leftover_bytes else f", leftover bytes={e.leftover_bytes}"))
                    raise Disconnection(400)
        except Disconnection as err:
            if err.transport_error is not None:
                self.writer.write(self.conn.send(ErrorPacket(err.transport_error)))
                await self.writer.drain()
            self.writer.close()
            await self.writer.wait_closed()
            logger.info("Client disconnected")
        finally:
            if (sess := SessionManager().by_client.get(self, None)) is not None:
                for s in sess:
                    logger.info(f"Session {s.session_id} removed")
            SessionManager().client_cleanup(self)

    async def propagate(self, request: Message, session: Session) -> TLObject | None:
        handler = self.server.handlers.get(request.obj.tlid())
        if handler is None:
            logger.warning(f"No handler found for obj: {request.obj}")
            return RpcResult(
                req_msg_id=request.message_id,
                result=RpcError(error_code=500, error_message="Not implemented"),
            )

        old_ctx = request_ctx.get()
        request_ctx.set(old_ctx.clone(obj=request.obj))

        result = None
        error = None

        try:
            result = await handler(self, request, session)
        except ErrorRpc as e:
            error = RpcError(error_code=e.error_code, error_message=e.error_message)
        except Exception as e:
            logger.warning(e)
            error = RpcError(error_code=500, error_message="Server error")

        request_ctx.set(old_ctx)

        result = result if error is None else error
        if result is None:
            logger.warning(f"Handler for function {request.obj} returned None!")
            result = RpcError(error_code=500, error_message="Server error")
        elif result is False:
            return

        if not isinstance(result, (Ping, Pong, RpcResult)):
            result = RpcResult(req_msg_id=request.message_id, result=result)

        return result
