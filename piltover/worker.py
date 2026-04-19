from __future__ import annotations

from inspect import getfullargspec
from io import BytesIO
from pathlib import Path
from typing import Awaitable, Callable, Any, TypeVar

from loguru import logger
from taskiq import InMemoryBroker, TaskiqEvents, AsyncTaskiqTask
from taskiq.brokers.inmemory_broker import InmemoryResultBackend
from taskiq.kicker import AsyncKicker

from piltover._faster_taskiq_inmemory_result_backend import FasterInmemoryResultBackend
from piltover.message_brokers.base_broker import BrokerType
from piltover.message_brokers.in_memory_broker import InMemoryMessageBroker
from piltover.message_brokers.rabbitmq_broker import RabbitMqMessageBroker
from piltover.pubsub.in_memory_pubsub import InMemoryPubSub
from piltover.session import SessionManager
from piltover.storage import LocalFileStorage
from piltover.tl.functions.internal import CallRpc, CallRpcInternal
from piltover.tl.types.internal import RpcResponse
from piltover.utils.debug import measure_time

try:
    from taskiq_aio_pika import AioPikaBroker
    from taskiq_redis import RedisAsyncResultBackend

    REMOTE_BROKER_SUPPORTED = True
except ImportError:
    AioPikaBroker = None
    RedisAsyncResultBackend = None
    REMOTE_BROKER_SUPPORTED = False

from piltover.context import RequestContext, request_ctx, NeedContextValuesContext
from piltover.db.models import User
from piltover.enums import ReqHandlerFlags
from piltover.exceptions import ErrorRpc
from piltover.tl import TLObject, RpcError, TLRequest, layer
from piltover.tl.core_types import RpcResult
from piltover.utils import get_public_key_fingerprint

T = TypeVar("T")
HandlerResult = Awaitable[T | None]
HandlerFunc = (Callable[[], HandlerResult] |
               Callable[[TLRequest[T]], HandlerResult] |
               Callable[[User], HandlerResult] |
               Callable[[TLRequest[T], User], HandlerResult])


class RequestHandler:
    __slots__ = (
        "func", "flags", "has_request_arg", "has_user_arg",
        "auth_required", "allow_mfa_pending", "bots_not_allowed", "refresh_session", "users_not_allowed", "is_internal",
        "has_user_id_arg", "dont_fetch_user", "prefetch_username",
    )

    def __init__(self, func: HandlerFunc, flags: int):
        self.func = func
        self.flags = flags
        func_args = set(getfullargspec(func).args)
        self.has_request_arg = "request" in func_args
        self.has_user_arg = "user" in func_args
        self.has_user_id_arg = "user_id" in func_args

        self.auth_required = not (self.flags & ReqHandlerFlags.AUTH_NOT_REQUIRED)
        self.allow_mfa_pending = bool(self.flags & ReqHandlerFlags.ALLOW_MFA_PENDING)
        self.bots_not_allowed = bool(self.flags & ReqHandlerFlags.BOT_NOT_ALLOWED)
        self.refresh_session = bool(self.flags & ReqHandlerFlags.REFRESH_SESSION)
        self.users_not_allowed = bool(self.flags & ReqHandlerFlags.USER_NOT_ALLOWED)
        self.is_internal = bool(self.flags & ReqHandlerFlags.INTERNAL)
        self.dont_fetch_user = bool(self.flags & ReqHandlerFlags.DONT_FETCH_USER)
        self.prefetch_username = bool(self.flags & ReqHandlerFlags.FETCH_USER_WITH_USERNAME)

    async def __call__(self, request: TLObject, user: User | None, user_id: int | None) -> Any:
        kwargs: dict = {}
        if self.has_request_arg:
            kwargs["request"] = request
        if self.has_user_arg:
            kwargs["user"] = user
        if self.has_user_id_arg:
            if user_id is not None:
                kwargs["user_id"] = user_id
            elif user is not None:
                kwargs["user_id"] = user.id
            else:
                kwargs["user_id"] = None

        return await self.func(**kwargs)


class MessageHandler:
    __slots__ = ("name", "registered", "request_handlers",)

    def __init__(self, name: str | None = None):
        self.name = name
        self.registered = False
        self.request_handlers: dict[int, RequestHandler] = {}

    def on_request(
            self, typ: type[TLRequest[T]], flags: ReqHandlerFlags = 0,
    ) -> Callable[[HandlerFunc[T]], HandlerFunc[T]]:
        def decorator(func: HandlerFunc[T]):
            if typ.tlid() in self.request_handlers:
                logger.warning("Overriding existing handler for {name} ({tlid:x})", name=typ.tlname(), tlid=typ.tlid())

            logger.trace(f"Added handler for function {typ.tlname()}" + (f" on {self.name}" if self.name else ""))

            self.request_handlers[typ.tlid()] = RequestHandler(func, flags)
            return func

        return decorator

    def register_handler(self, handler: MessageHandler, clear: bool = True):
        if handler.registered:
            raise RuntimeError(f"Handler {handler} already registered!")

        for new_handler_id in handler.request_handlers:
            if new_handler_id in self.request_handlers:
                logger.warning(f"Overriding existing handler for ({hex(new_handler_id)[2:]})")

        self.request_handlers.update(handler.request_handlers)
        if clear:
            handler.request_handlers.clear()

        handler.registered = True


class Worker(MessageHandler):
    RMQ_HOST = "amqp://guest:guest@127.0.0.1:5672"
    REDIS_HOST = "redis://127.0.0.1"

    def __init__(
            self, data_dir: Path, public_key: str,
            rabbitmq_address: str | None = RMQ_HOST, redis_address: str | None = REDIS_HOST,
    ):
        super().__init__()

        self._storage = LocalFileStorage(data_dir)
        self.public_key = public_key
        self.fingerprint: int = get_public_key_fingerprint(self.public_key)

        if not REMOTE_BROKER_SUPPORTED or rabbitmq_address is None or redis_address is None:
            logger.info("Worker is initializing with InMemoryBroker")
            self.broker = InMemoryBroker(
                max_async_tasks=128,
                cast_types=False,
            ).with_result_backend(FasterInmemoryResultBackend())
            self.message_broker = InMemoryMessageBroker()
        else:
            logger.info("Worker is initializing with AioPikaBroker + RedisAsyncResultBackend")
            self.broker = AioPikaBroker(rabbitmq_address).with_result_backend(RedisAsyncResultBackend(redis_address))
            self.message_broker = RabbitMqMessageBroker(BrokerType.WRITE, rabbitmq_address)

        # TODO: add RedisPubSub
        self.pubsub = InMemoryPubSub()

        # self.broker.register_task(self._handle_tl_rpc, "handle_tl_rpc")
        self.broker.register_task(self._handle_tl_rpc_measure_time, "handle_tl_rpc")
        self.broker.register_task(self._handle_tl_rpc_internal, "handle_tl_rpc_internal")
        self.broker.add_event_handler(TaskiqEvents.WORKER_STARTUP, self._broker_startup)
        self.broker.add_event_handler(TaskiqEvents.WORKER_SHUTDOWN, self._broker_shutdown)

    async def _broker_startup(self, _) -> None:
        await self.message_broker.startup()
        SessionManager.set_broker(self.message_broker)
        await self.pubsub.startup()

    async def _broker_shutdown(self, _) -> None:
        await self.message_broker.shutdown()
        await self.pubsub.shutdown()

    async def call_internal(self, request: TLObject) -> AsyncTaskiqTask[TLObject]:
        return await AsyncKicker(
            task_name="handle_tl_rpc_internal",
            broker=self.broker,
            labels={},
        ).kiq(
            call=CallRpcInternal(obj=request).write().hex(),
        )

    @classmethod
    async def get_user(cls, call: CallRpc, allow_mfa_pending: bool = False, with_username: bool = False) -> User | None:
        if call.user_id is None or call.auth_id is None:
            return None
        if call.mfa_pending and not allow_mfa_pending:
            raise ErrorRpc(error_code=401, error_message="SESSION_PASSWORD_NEEDED")

        query = User.get_or_none(id=call.user_id, userauthorizations__id=call.auth_id)
        if with_username:
            query = query.select_related("username")

        return await query

    async def _handle_tl_rpc_measure_time(self, call_hex: str) -> RpcResponse:
        with measure_time("_handle_tl_rpc()"):
            return await self._handle_tl_rpc(call_hex)

    def _err_response(self, req_msg_id: int, code: int, message: str) -> RpcResponse | str:
        response = RpcResponse(obj=RpcResult(
            req_msg_id=req_msg_id,
            result=RpcError(error_code=code, error_message=message),
        ))

        if isinstance(self.broker.result_backend, InmemoryResultBackend):
            return response
        else:
            return response.write().hex()

    def _err_response_internal(self, code: int, message: str) -> RpcError | str:
        response = RpcError(error_code=code, error_message=message)

        if isinstance(self.broker.result_backend, InmemoryResultBackend):
            return response
        else:
            return response.write().hex()

    async def _handle_tl_rpc(self, call_hex: str) -> RpcResponse | str:
        with measure_time("read CallRpc"):
            call = CallRpc.read(BytesIO(bytes.fromhex(call_hex)), True)

        logger.trace("Got request: {call!r}", call=call)

        if not (handler := self.request_handlers.get(call.obj.tlid())) or handler.is_internal:
            logger.warning("No handler found for obj: {obj}", obj=call.obj)
            return self._err_response(call.message_id, 500, "NOT_IMPLEMENTED")
        if handler.is_internal:
            logger.warning("Client tried to execute internal request: {call!r}", call=call)
            return self._err_response(call.message_id, 500, "NOT_IMPLEMENTED")

        # TODO: send this error from gateway
        if call.is_bot and handler.bots_not_allowed:
            return self._err_response(call.message_id, 400, "BOT_METHOD_INVALID")
        elif not call.is_bot and handler.users_not_allowed:
            return self._err_response(call.message_id, 400, "USER_BOT_REQUIRED")

        user = None
        if (handler.auth_required or handler.has_user_arg) and not handler.dont_fetch_user:
            try:
                with measure_time(".get_user(...)"):
                    user = await self.get_user(call, handler.allow_mfa_pending, handler.prefetch_username)
            except ErrorRpc as e:
                return self._err_response(call.message_id, e.error_code, e.error_message)

            if user is None and handler.auth_required:
                return self._err_response(call.message_id, 401, "AUTH_KEY_UNREGISTERED")
        elif handler.dont_fetch_user and handler.auth_required \
                and (not call.user_id or (call.mfa_pending and not handler.allow_mfa_pending)):
            return self._err_response(call.message_id, 401, "AUTH_KEY_UNREGISTERED")

        ctx_token = request_ctx.set(RequestContext(
            call.auth_key_id, call.perm_auth_key_id, call.message_id, call.session_id, call.obj, call.layer,
            call.auth_id, call.user_id, self, self._storage,
        ))

        try:
            with measure_time(f"handler({call.obj.tlname()})"):
                # TODO: wrap handler call in in_transaction?
                result = await handler(call.obj, user, call.user_id)
        except ErrorRpc as e:
            reason = f", reason: {e.reason}" if e.reason is not None else ""
            logger.warning(f"{call.obj.tlname()}: [{e.error_code} {e.error_message}]{reason}")
            result = RpcError(error_code=e.error_code, error_message=e.error_message)
        except Exception as e:
            logger.opt(exception=e).warning(f"Error while processing {call.obj.tlname()}")
            result = RpcError(error_code=500, error_message="Server error")
        finally:
            request_ctx.reset(ctx_token)

        if result is None:
            logger.warning(f"Handler for {call.obj} returned None")
            result = RpcError(error_code=500, error_message="NOT_IMPLEMENTED")

        result_obj = RpcResult(
            req_msg_id=call.message_id,
            result=result,
        )

        if not isinstance(result_obj.result, RpcError):
            ctx = NeedContextValuesContext()
            result_obj.check_for_ctx_values(ctx)
            if ctx.any():
                result_obj = ctx.to_tl(result_obj)

        logger.trace("Returning to gateway: {result!r}", result=result_obj)

        response = RpcResponse(
            obj=result_obj,
            refresh_auth=handler.refresh_session,
        )

        if isinstance(self.broker.result_backend, InmemoryResultBackend):
            return response
        else:
            return response.write().hex()

    async def _handle_tl_rpc_internal(self, call: str) -> Any:
        with measure_time("read CallRpc"):
            call = CallRpcInternal.read(BytesIO(bytes.fromhex(call)), True)

        logger.trace("Got internal request: {call!r}", call=call)

        if not (handler := self.request_handlers.get(call.obj.tlid())):
            logger.warning("No handler found for obj: {obj}", obj=call.obj)
            return self._err_response_internal(500, "NOT_IMPLEMENTED")
        if not handler.is_internal:
            logger.warning("Tried to execute non-internal request: {call!r}", call=call)
            return self._err_response_internal(500, "ERROR_METHOD_NOT_INTERNAL")

        ctx_token = request_ctx.set(RequestContext(
            0, 0, 0, 0, call.obj, layer, call.as_auth_id or 0, call.as_user or 0, self, self._storage,
        ))

        try:
            with measure_time(f"internal_handler({call.obj.tlname()})"):
                # TODO: wrap handler call in in_transaction?
                result = await handler(call.obj, None, None)
        except ErrorRpc as e:
            reason = f", reason: {e.reason}" if e.reason is not None else ""
            logger.warning(f"{call.obj.tlname()}: [{e.error_code} {e.error_message}]{reason}")
            result = RpcError(error_code=e.error_code, error_message=e.error_message)
        except Exception as e:
            logger.opt(exception=e).warning(f"Error while processing {call.obj.tlname()}")
            result = RpcError(error_code=500, error_message="Server error")
        finally:
            request_ctx.reset(ctx_token)

        if result is None:
            logger.warning(f"Handler for {call.obj} returned None")
            result = RpcError(error_code=500, error_message="NOT_IMPLEMENTED")

        logger.trace("Returning internal result: {result!r}", result=result)

        if isinstance(self.broker.result_backend, InmemoryResultBackend):
            return result
        else:
            return result.write().hex()
