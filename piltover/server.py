import asyncio
import hashlib
import os
import secrets
import time
from collections import defaultdict
from io import BytesIO
from types import SimpleNamespace
from typing import Callable, Awaitable

import tgcrypto
from loguru import logger

from piltover.connection import Connection
from piltover.context import RequestContext, request_ctx
from piltover.enums import Transport
from piltover.exceptions import Disconnection, ErrorRpc, InvalidConstructorException
from piltover.session_manager import Session, SessionManager
from piltover.tl.types import (
    CoreMessage,
    EncryptedMessage,
    DecryptedMessage,
    UnencryptedMessage,
)
from piltover.tl_new import TLObject, SerializationUtils, ResPQ, Int, Long, PQInnerData, ReqPqMulti, ReqPq, ReqDHParams, \
    SetClientDHParams, PQInnerDataDc, PQInnerDataTempDc, DhGenOk, Ping
from piltover.tl_new.core_types import MsgContainer, Message, RpcResult
from piltover.tl_new.types import ServerDHInnerData, ServerDHParamsOk, ClientDHInnerData, RpcError, Pong, MsgsAck
from piltover.tl_new.utils import is_content_related
from piltover.types import Keys
from piltover.utils import (
    read_int,
    generate_large_prime,
    gen_safe_prime,
    gen_keys,
    get_public_key_fingerprint,
    restore_private_key,
    restore_public_key,
    kdf,
    background,
)
from piltover.utils.buffered_stream import BufferedStream
from piltover.utils.rsa_utils import rsa_decrypt, rsa_pad_inverse


class MessageHandler:
    def __init__(self, name: str = None):
        self.name = name
        self.server: Server | None = None
        self.handlers: defaultdict[
            int,
            set[Callable[[Client, CoreMessage, Session], Awaitable[TLObject | dict | None]]],
        ] = defaultdict(set)

    def on_message(self, typ: type[TLObject]):
        def decorator(func: Callable[[Client, CoreMessage, Session], Awaitable[TLObject | dict | None]]):
            logger.debug("Added handler for function {typ!r}" + (f" on {self.name}" if self.name else ""),
                         typ=typ.tlname())

            self.handlers[typ.tlid()].add(func)
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

        self.public_key = restore_public_key(self.server_keys.public_key)
        self.private_key = restore_private_key(self.server_keys.private_key)

        self.fingerprint: int = get_public_key_fingerprint(self.server_keys.public_key)

        self.clients: dict[str, Client] = {}
        self.handlers: defaultdict[
            int,
            set[Callable[[Client, CoreMessage, Session], Awaitable[TLObject | dict | None]]],
        ] = defaultdict(set)
        self.sys_handlers = defaultdict(list)
        self.salt: int = 0

    @logger.catch
    async def handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        try:
            # Check the transport: https://core.telegram.org/mtproto/mtproto-transports

            stream = BufferedStream(reader=reader, writer=writer)

            # https://docs.python.org/3/library/asyncio-protocol.html#asyncio.BaseTransport.get_extra_info
            extra = writer.get_extra_info("peername")
            header = await stream.peek(1)

            if header == b"\xef":
                await stream.read(1)  # discard
                # TCP Abridged
                transport = Transport.Abridged
            elif header == b"\xee":
                await stream.read(1)  # discard
                # TCP Intermediate
                # 0xeeeeeeee
                assert await stream.read(3) == b"\xee\xee\xee", "Invalid TCP Intermediate header"
                transport = Transport.Intermediate
            elif header == b"\xdd":
                await stream.read(1)  # discard
                # Padded Intermediate
                # 0xdddddddd
                assert await stream.read(3) == b"\xdd\xdd\xdd", "Invalid TCP Intermediate header"
                transport = Transport.PaddedIntermediate
            else:
                # The seq_no in TCPFull always starts with 0, so we can recognize
                # the transport and distinguish it from obfuscated ones (starting with 64 random bytes)
                # by checking whether the seq_no bytes are zeroed
                soon = await stream.peek(8)
                if soon[-4:] == b"\0\0\0\0":
                    transport = Transport.Full
                else:
                    # Obfuscated Transports
                    transport = Transport.Obfuscated

            assert transport is not None, f"Transport is None, aborting... (header: {header})"
            logger.info(f"Connected client with {transport} {extra}")

            await self.welcome(stream=stream, transport=transport)
        except Disconnection:
            logger.error("Client disconnected before even trying to generate an auth key :(")

    async def welcome(self, stream: BufferedStream, transport: Transport):
        client = Client(
            transport=transport,
            server=self,
            stream=stream,
            peername=stream.get_extra_info("peername"),
        )
        background(client.worker())

    async def serve(self):
        server = await asyncio.start_server(self.handle, self.HOST, self.PORT)
        async with server:
            await server.serve_forever()

    async def register_auth_key(self, auth_key_id: int, auth_key: bytes):
        for handler in self.sys_handlers["auth_key_set"]:
            await handler(auth_key_id, auth_key)

    async def get_auth_key(self, auth_key_id: int) -> tuple[int, bytes] | None:
        for handler in self.sys_handlers["auth_key_get"]:
            if (auth_key_info := await handler(auth_key_id)) is not None:
                return auth_key_info

    def on_message(self, typ: type[TLObject]):
        def decorator(func: Callable[[Client, CoreMessage, Session], Awaitable[TLObject | bool | None]]):
            logger.debug("Added handler for function {typ!r}", typ=typ)

            self.handlers[typ.tlid()].add(func)
            return func

        return decorator

    def register_handler(self, handler: MessageHandler) -> None:
        if handler.server is not None:
            raise RuntimeError(f"Handler {handler} already registered!")
        for tlid, handlers in handler.handlers.items():
            self.handlers[tlid].update(handlers)

        handler.server = self

    def on_auth_key_set(self, func: Callable[[int, bytes], Awaitable[None]]):
        self.sys_handlers["auth_key_set"].append(func)
        return func

    def on_auth_key_get(self, func: Callable[[int], Awaitable[tuple[int, bytes] | None]]):
        self.sys_handlers["auth_key_get"].append(func)
        return func


class Client:
    def __init__(self, server: Server, transport: Transport, stream: BufferedStream, peername: tuple):
        self.server: Server = server
        self.peername: tuple = peername

        self.conn: Connection = Connection.new(transport=transport, stream=stream)

        self.auth_data = None
        self.empty_session = Session(self, 0)

    async def read_message(self) -> EncryptedMessage | UnencryptedMessage:
        data = BytesIO(await self.conn.recv())
        auth_key_id = Long.read(data)
        if auth_key_id == 0:
            message_id = Long.read(data)
            message_data_length = Int.read(data)
            message_data = data.read(message_data_length)
            return UnencryptedMessage(message_id, message_data)
        msg_key = data.read(16)
        encrypted_data = data.read()
        return EncryptedMessage(auth_key_id, msg_key, encrypted_data)

    async def send(self, objects: TLObject | list[tuple[TLObject, CoreMessage]], session: Session,
                   originating_request: CoreMessage | None = None, in_reply: bool = True):
        serialized, out_seq = self.serialize_message(
            session,
            objects,
            originating_request=originating_request.message_id if originating_request is not None else None,
        )
        await self.conn.send(await self.encrypt(serialized, out_seq, session, in_reply=in_reply))

    async def send_unencrypted(self, obj: TLObject) -> None:
        obj = obj.write()
        await self.conn.send(
            bytes(8)
            + Long.write(self.empty_session.msg_id(in_reply=True))
            + Int.write(len(obj)) + obj
        )

    async def handle_unencrypted_message(self, obj: TLObject):
        if isinstance(obj, (ReqPqMulti, ReqPq)):
            req_pq_multi = obj
            p = generate_large_prime(31)
            q = generate_large_prime(31)

            if p > q:
                p, q = q, p

            self.auth_data = SimpleNamespace()
            self.auth_data.p, self.auth_data.q = p, q

            assert p != -1, "p is -1"
            assert q != -1, "q is -1"
            assert p != q

            pq = self.auth_data.p * self.auth_data.q
            # ic(p, q, pq)

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

            assert len(req_dh_params.p) == 4, f"client_p size must be 4 bytes, not {len(req_dh_params.p)}"
            assert len(req_dh_params.q) == 4, f"client_q size must be 4 bytes, not {len(req_dh_params.q)}"
            client_p = int.from_bytes(req_dh_params.p, "big", signed=False)
            client_q = int.from_bytes(req_dh_params.q, "big", signed=False)
            assert client_p == self.auth_data.p, "client_p is different than server_p"
            assert client_q == self.auth_data.q, "client_q is different than server_q"

            assert self.auth_data.server_nonce == req_dh_params.server_nonce
            # TODO: check server_nonce in other places too

            # print(f"{client_p=} {client_q=}")

            encrypted_data: bytes = req_dh_params.encrypted_data
            assert len(encrypted_data) == 256, "Invalid encrypted data"

            old = False
            key_aes_encrypted = rsa_decrypt(encrypted_data, self.server.public_key, self.server.private_key)
            try:
                key_aes_encrypted = rsa_pad_inverse(key_aes_encrypted)
            except AssertionError as e:
                logger.debug(f"rsa_pad_inverse raised error: {e}. Using old pre-RSA_PAD encryption.")
                old = True
            key_aes_encrypted = key_aes_encrypted.lstrip(b"\0")

            # idk TODO: restart generation with dh_fail instead
            # assert key_aes_encrypted >= public.n, "key_aes_encrypted greater than RSA modulus, aborting..."

            if old:
                p_q_inner_data = PQInnerData.read(BytesIO(key_aes_encrypted[20:]))

                digest = key_aes_encrypted[:20]
                assert hashlib.sha1(p_q_inner_data.write()).digest() == digest, "sha1 of data doesn't match"
            else:
                p_q_inner_data = PQInnerData.read(BytesIO(key_aes_encrypted))

            assert isinstance(p_q_inner_data, (PQInnerData, PQInnerDataDc, PQInnerDataTempDc)), \
                f"Expected p_q_inner_data_*, got instead {type(p_q_inner_data)}"

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
            assert self.auth_data
            assert hasattr(self.auth_data, "tmp_aes_key")
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
            )
            logger.info("Auth key generation successfully completed!")
        elif isinstance(obj, MsgsAck):
            pass
        else:
            raise RuntimeError(f"Received unexpected unencrypted message: {obj}")  # TODO right error

    async def handle_encrypted_message(self, core_message: CoreMessage, session_id: int):
        sess = SessionManager().get_or_create(self, session_id)
        sess.update_incoming_content_related_msgs(core_message.obj, core_message.seq_no)

        if (result := await self.propagate(core_message, sess)) is None:
            return
        await self.send(
            result,
            sess,
            originating_request=(None if isinstance(core_message.obj, MsgContainer) else core_message),
        )

    async def recv(self):
        message = await self.read_message()
        if isinstance(message, EncryptedMessage):
            decrypted = await self.decrypt(message)
            core_message = decrypted.to_core_message()
            request_ctx.set(
                RequestContext(message.auth_key_id, decrypted.message_id, decrypted.session_id, core_message.obj)
            )

            logger.debug(core_message)
            await self.handle_encrypted_message(core_message, decrypted.session_id)
        elif isinstance(message, UnencryptedMessage):
            decoded = SerializationUtils.read(BytesIO(message.message_data), TLObject)
            logger.debug(decoded)
            await self.handle_unencrypted_message(decoded)

    # TODO don't mix list and non-list parameters
    def serialize_message(self, session: Session, objects: TLObject | list[tuple[TLObject, CoreMessage]],
                          originating_request: int | None = None) -> tuple[bytes, int]:
        if isinstance(objects, TLObject):
            final_obj = objects
            serialized = objects.write()

            if originating_request is None:
                msg_id = session.msg_id(in_reply=False)
            else:
                # TODO check
                if is_content_related(objects):
                    msg_id = session.msg_id(in_reply=True)
                else:
                    msg_id = originating_request + 1
            seq_no = session.get_outgoing_seq_no(objects)
        else:
            container = MsgContainer(messages=[])
            for obj, core_message in objects:
                # TODO what if there is no core_message (rename it to originating_request too)
                if is_content_related(obj):
                    msg_id = session.msg_id(in_reply=True)
                else:
                    # suspicious
                    msg_id = core_message.message_id + 1
                seq_no = session.get_outgoing_seq_no(obj)

                container.messages.append(Message(message_id=msg_id, seq_no=seq_no, obj=obj))

            final_obj = container
            serialized = container.write()

        return serialized, session.get_outgoing_seq_no(final_obj)

    async def encrypt(self, serialized: bytes, out_seq: int, session: Session, in_reply: bool = True) -> bytes:
        if self.auth_data.auth_key is None:
            assert False, "FATAL: self.auth_key is None"
        elif self.auth_data.auth_key_id is None:
            assert False, "FATAL: self.auth_key_id is None"

        data = (
                Long.write(self.server.salt)
                + Long.write(session.session_id)
                + Long.write(session.msg_id(in_reply=in_reply))
                + Int.write(out_seq)
                + len(serialized).to_bytes(4, "little")
                + serialized
        )

        padding = os.urandom(-(len(data) + 12) % 16 + 12)

        # 96 = 88 + 8 (8 = incoming message (server message); 0 = outgoing (client message))
        msg_key_large = hashlib.sha256(self.auth_data.auth_key[96: 96 + 32] + data + padding).digest()
        msg_key = msg_key_large[8:24]
        aes_key, aes_iv = kdf(self.auth_data.auth_key, msg_key, False)

        result = (
                Long.write(self.auth_data.auth_key_id)
                + msg_key
                + tgcrypto.ige256_encrypt(data + padding, aes_key, aes_iv)
        )
        return result

    async def decrypt(self, message: EncryptedMessage) -> DecryptedMessage:
        if self.auth_data is None or not hasattr(self.auth_data, "auth_key") \
                or not hasattr(self.auth_data, "auth_key_id") or self.auth_data.auth_key_id != message.auth_key_id:
            got = await self.server.get_auth_key(message.auth_key_id)
            if got is None:
                logger.info("Client sent unknown auth_key_id, disconnecting")
                raise Disconnection(404)
            self.auth_data = SimpleNamespace()
            self.auth_data.auth_key_id, self.auth_data.auth_key = got

        aes_key, aes_iv = kdf(self.auth_data.auth_key, message.msg_key, True)

        decrypted = BytesIO(tgcrypto.ige256_decrypt(message.encrypted_data, aes_key, aes_iv))
        salt = decrypted.read(8)
        session_id = Long.read(decrypted)
        message_id = Long.read(decrypted)
        seq_no = Int.read(decrypted)
        message_data_length = Int.read(decrypted)
        return DecryptedMessage(
            salt,
            session_id,
            message_id,
            seq_no,
            decrypted.read(message_data_length),
            decrypted.read(),
        )

    @logger.catch
    async def worker(self):
        try:
            self.conn = await self.conn.init()

            while True:
                try:
                    await self.recv()
                except AssertionError:
                    logger.exception("Unexpected failed assertion", backtrace=True)
                except InvalidConstructorException as e:
                    if e.wrong_type:
                        continue
                    logger.error(f"Invalid constructor: {e.constructor}")
                    raise Disconnection(400)
        except Disconnection as err:
            if err.transport_error is not None:
                await self.conn.send(int.to_bytes(err.transport_error, 4, "little", signed=True))
            await self.conn.close()
            logger.info("Client disconnected")
        finally:
            SessionManager().client_cleanup(self)

    def to_core_message(self, msg: Message | CoreMessage) -> CoreMessage:
        if isinstance(msg, Message):
            return CoreMessage(message_id=msg.message_id, seq_no=msg.seq_no, obj=msg.obj)
        return msg

    async def propagate(self, request: CoreMessage | Message, session: Session) -> list[tuple[TLObject, CoreMessage]] | TLObject | None:
        if isinstance(request.obj, MsgContainer):
            results = []
            for msg in request.obj.messages:
                msg = self.to_core_message(msg)

                result = await self.propagate(msg, session)
                if result is None:
                    continue
                results.append((result, msg))

            if not results:
                logger.warning("Empty msg_container, returning...")
                return

            return results
        else:
            handlers = self.server.handlers.get(request.obj.tlid(), [])

            result = None
            error = None
            for rpc in handlers:
                try:
                    result = await rpc(self, request, session)
                    if result is not None:
                        break
                except ErrorRpc as e:
                    if error is None:
                        error = RpcError(error_code=e.error_code, error_message=e.error_message)
                except Exception as e:
                    logger.warning(e)
                    if error is None:
                        error = RpcError(error_code=500, error_message="Server error")

            result = result if error is None else error
            if result is None:
                logger.warning("No handler found for obj:\n{obj}", obj=request.obj)
                result = RpcError(error_code=500, error_message="Not implemented")
            if result is False:
                return

            if not isinstance(result, (Ping, Pong, RpcResult)):
                result = RpcResult(req_msg_id=request.message_id, result=result)

            return result
