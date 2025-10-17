from __future__ import annotations

from inspect import getfullargspec
from io import BytesIO
from pathlib import Path
from time import perf_counter
from typing import Awaitable, Callable, Any, TypeVar

from loguru import logger
from taskiq import InMemoryBroker, TaskiqEvents

from piltover._faster_taskiq_inmemory_result_backend import FasterInmemoryResultBackend
from piltover.message_brokers.base_broker import BrokerType
from piltover.message_brokers.in_memory_broker import InMemoryMessageBroker
from piltover.message_brokers.rabbitmq_broker import RabbitMqMessageBroker
from piltover.session_manager import SessionManager
from piltover.storage import LocalFileStorage
from piltover.tl.functions.internal import CallRpc
from piltover.tl.types.internal import RpcResponse

try:
    from taskiq_aio_pika import AioPikaBroker
    from taskiq_redis import RedisAsyncResultBackend

    REMOTE_BROKER_SUPPORTED = True
except ImportError:
    AioPikaBroker = None
    RedisAsyncResultBackend = None
    REMOTE_BROKER_SUPPORTED = False

from piltover.context import RequestContext, request_ctx
from piltover.db.models import UserAuthorization, User
from piltover.enums import ReqHandlerFlags
from piltover.exceptions import ErrorRpc
from piltover.tl import TLObject, RpcError, TLRequest
from piltover.tl.core_types import RpcResult
from piltover.utils import Keys, get_public_key_fingerprint

T = TypeVar("T")
HandlerResult = Awaitable[T | None]
HandlerFunc = (Callable[[], HandlerResult] |
               Callable[[TLRequest[T]], HandlerResult] |
               Callable[[User], HandlerResult] |
               Callable[[TLRequest[T], User], HandlerResult])


class RequestHandler:
    __slots__ = ("func", "flags", "has_request_arg", "has_user_arg",)

    def __init__(self, func: HandlerFunc, flags: int):
        self.func = func
        self.flags = flags
        func_args = set(getfullargspec(func).args)
        self.has_request_arg = "request" in func_args
        self.has_user_arg = "user" in func_args

    def auth_required(self) -> bool:
        return not (self.flags & ReqHandlerFlags.AUTH_NOT_REQUIRED)

    def allow_mfa_pending(self) -> bool:
        return bool(self.flags & ReqHandlerFlags.ALLOW_MFA_PENDING)

    async def __call__(self, request: TLObject, user: User | None) -> Any:
        kwargs = {}
        if self.has_request_arg: kwargs["request"] = request
        if self.has_user_arg: kwargs["user"] = user

        return await self.func(**kwargs)


class MessageHandler:
    __slots__ = ("name", "registered", "request_handlers",)

    def __init__(self, name: str | None = None):
        self.name = name
        self.registered = False
        self.request_handlers: dict[int, RequestHandler] = {}

    def on_request(self, typ: type[TLRequest[T]], flags: int = 0) -> Callable[[HandlerFunc[T]], HandlerFunc[T]]:
        def decorator(func: HandlerFunc[T]):
            logger.trace(f"Added handler for function {typ.tlname()}" + (f" on {self.name}" if self.name else ""))

            self.request_handlers[typ.tlid()] = RequestHandler(func, flags)
            return func

        return decorator

    def register_handler(self, handler: MessageHandler, clear: bool = True):
        if handler.registered:
            raise RuntimeError(f"Handler {handler} already registered!")

        self.request_handlers.update(handler.request_handlers)
        if clear:
            handler.request_handlers.clear()

        handler.registered = True


class Worker(MessageHandler):
    RMQ_HOST = "amqp://guest:guest@127.0.0.1:5672"
    REDIS_HOST = "redis://127.0.0.1"

    def __init__(
            self, data_dir: Path, server_keys: Keys,
            rabbitmq_address: str | None = RMQ_HOST, redis_address: str | None = REDIS_HOST,
    ):
        super().__init__()

        self._storage = LocalFileStorage(data_dir)
        self.server_keys = server_keys
        self.fingerprint: int = get_public_key_fingerprint(self.server_keys.public_key)

        if not REMOTE_BROKER_SUPPORTED or rabbitmq_address is None or redis_address is None:
            logger.info("Worker is initializing with InMemoryBroker")
            self.broker = InMemoryBroker().with_result_backend(FasterInmemoryResultBackend())
            self.message_broker = InMemoryMessageBroker()
        else:
            logger.info("Worker is initializing with AioPikaBroker + RedisAsyncResultBackend")
            self.broker = AioPikaBroker(rabbitmq_address, result_backend=RedisAsyncResultBackend(redis_address))
            self.message_broker = RabbitMqMessageBroker(BrokerType.WRITE, rabbitmq_address)

        self.broker.register_task(self._handle_tl_rpc, "handle_tl_rpc")
        self.broker.add_event_handler(TaskiqEvents.WORKER_STARTUP, self._broker_startup)
        self.broker.add_event_handler(TaskiqEvents.WORKER_SHUTDOWN, self._broker_shutdown)

    async def _broker_startup(self, _) -> None:
        await self.message_broker.startup()
        SessionManager.set_broker(self.message_broker)

    async def _broker_shutdown(self, _) -> None:
        await self.message_broker.shutdown()

    @classmethod
    async def get_user(cls, call: CallRpc, allow_mfa_pending: bool = False) -> User | None:
        if call.user_id is None or call.auth_id is None:
            return None

        auth = await UserAuthorization.get_or_none(user__id=call.user_id, id=call.auth_id).select_related("user")
        if auth is not None and not allow_mfa_pending and auth.mfa_pending:
            raise ErrorRpc(error_code=401, error_message="SESSION_PASSWORD_NEEDED")

        return auth.user if auth is not None else None

    async def _handle_tl_rpc_measure_time(self, call_hex: str) -> RpcResponse:
        time_start = perf_counter()
        result = await self._handle_tl_rpc(call_hex)
        logger.trace(f"Rpc call processing took {(perf_counter() - time_start) * 1000:.2f} ms")
        return result

    async def _handle_tl_rpc(self, call_hex: str) -> RpcResponse:
        call = CallRpc.read(BytesIO(bytes.fromhex(call_hex)), True)

        #obj, call.obj = call.obj, None
        #logger.trace(f"Got CallRpc: {call!r}")
        #call.obj = obj

        if not (handler := self.request_handlers.get(call.obj.tlid())):
            logger.warning(f"No handler found for obj: {call.obj}")
            return RpcResponse(obj=RpcResult(
                req_msg_id=call.message_id,
                result=RpcError(error_code=500, error_message="Not implemented"),
            ))

        request_ctx.set(RequestContext(
            call.auth_key_id, call.perm_auth_key_id, call.message_id, call.session_id, call.obj, call.layer,
            call.auth_id, call.user_id, self, self._storage,
        ))

        user = None
        if handler.auth_required() or (call.user_id is not None and call.auth_id is not None):
            try:
                user = await self.get_user(call, handler.allow_mfa_pending())
            except ErrorRpc as e:
                return RpcResponse(obj=RpcResult(
                    req_msg_id=call.message_id,
                    result=RpcError(error_code=e.error_code, error_message=e.error_message),
                ))

            if user is None:
                return RpcResponse(obj=RpcResult(
                    req_msg_id=call.message_id,
                    result=RpcError(error_code=401, error_message="AUTH_KEY_UNREGISTERED"),
                ))

        try:
            result = await handler(call.obj, user)
        except ErrorRpc as e:
            reason = f", reason: {e.reason}" if e.reason is not None else ""
            logger.warning(f"{call.obj.tlname()}: [{e.error_code} {e.error_message}]{reason}")
            result = RpcError(error_code=e.error_code, error_message=e.error_message)
        except Exception as e:
            logger.opt(exception=e).warning(f"Error while processing {call.obj.tlname()}")
            result = RpcError(error_code=500, error_message="Server error")

        if result is None:
            logger.warning(f"Handler for {call.obj} returned None")
            result = RpcError(error_code=500, error_message="Not implemented")

        #logger.trace(f"Returning from worker: {type(result)}, {result}")
        return RpcResponse(obj=RpcResult(
            req_msg_id=call.message_id,
            result=result,
        ))
