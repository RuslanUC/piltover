from __future__ import annotations

from inspect import getfullargspec
from io import BytesIO
from pathlib import Path
from typing import Callable, Any, TypeVar, cast, Protocol, ParamSpec, Awaitable

import nats
from loguru import logger
from nats.aio.msg import Msg as NatsMsg

from piltover.config import SYSTEM_CONFIG
from piltover.context import RequestContext, request_ctx, NeedContextValuesContext
from piltover.db.models import User
from piltover.enums import ReqHandlerFlags
from piltover.exceptions import ErrorRpc
from piltover.storage import LocalFileStorage
from piltover.tl import TLObject, RpcError, TLRequest
from piltover.tl.core_types import RpcResult
from piltover.tl.functions.internal import CallRpc, CallRpcInternal
from piltover.tl.layer_info import layer
from piltover.tl.types.internal import RpcResponse, NeedsContextValues
from piltover.utils import get_public_key_fingerprint
from piltover.utils.debug import measure_time

T = TypeVar("T", covariant=True)
RequestT = TypeVar("RequestT", bound=TLRequest, contravariant=True)
P = ParamSpec("P")


class HandlerFunc(Protocol[T]):
    async def __call__(self, *args, **kwargs) -> T:
        ...


class RequestHandler:
    __slots__ = (
        "func", "flags", "has_request_arg", "has_user_arg",
        "auth_required", "allow_mfa_pending", "bots_not_allowed", "refresh_session", "users_not_allowed", "is_internal",
        "has_user_id_arg", "dont_fetch_user", "prefetch_username",
    )

    def __init__(self, func: HandlerFunc[Any], flags: int):
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
            self, typ: type[TLRequest[T]], flags: ReqHandlerFlags = ReqHandlerFlags.NONE,
    ) -> Callable[[Callable[P, Awaitable[T]]], Callable[P, Awaitable[T]]]:
        def decorator(func: Callable[P, Awaitable[T]]) -> Callable[P, Awaitable[T]]:
            if typ.tlid() in self.request_handlers:
                logger.warning("Overriding existing handler for {name} ({tlid:x})", name=typ.tlname(), tlid=typ.tlid())

            logger.trace(f"Added handler for function {typ.tlname()}" + (f" on {self.name}" if self.name else ""))

            self.request_handlers[typ.tlid()] = RequestHandler(func, flags)
            return func

        return decorator

    def register_handler(self, handler: MessageHandler, clear: bool = True):
        if handler.registered:
            raise RuntimeError(f"Handler {handler.name!r} already registered!")

        for new_handler_id in handler.request_handlers:
            if new_handler_id in self.request_handlers:
                logger.warning(f"Overriding existing handler for ({hex(new_handler_id)[2:]})")

        self.request_handlers.update(handler.request_handlers)
        if clear:
            handler.request_handlers.clear()

        handler.registered = True


NATS_WORKER_RPC_SUBJECT = "piltover.worker.handle_tl_rpc"
NATS_WORKER_RPC_RESPONSE_SUBJECT = "piltover.session.{key_id}-{session_id}.rpc_response.{req_msg_id}"
NATS_WORKER_RPC_INTERNAL_SUBJECT = "piltover.worker.handle_tl_rpc_internal"


class Worker(MessageHandler):
    def __init__(self, data_dir: Path, public_key: str) -> None:
        super().__init__()

        self._storage = LocalFileStorage(data_dir)
        self.public_key = public_key
        self.fingerprint = get_public_key_fingerprint(self.public_key)

        self.nc = nats.NATS()

    async def start(self) -> None:
        await self.nc.connect(SYSTEM_CONFIG.nats_address)
        await self.nc.subscribe(NATS_WORKER_RPC_SUBJECT, "piltover-worker", cb=self._handle_tl_rpc_measure_time)
        await self.nc.subscribe(NATS_WORKER_RPC_INTERNAL_SUBJECT, "piltover-worker", cb=self._handle_tl_rpc_internal)

    async def call_internal(self, request: TLObject) -> None:
        await self.nc.publish(NATS_WORKER_RPC_INTERNAL_SUBJECT, CallRpcInternal(obj=request).write())

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

    async def _handle_tl_rpc_measure_time(self, msg: NatsMsg) -> None:
        with measure_time("_handle_tl_rpc()"):
            return await self._handle_tl_rpc(msg)

    async def _rpc_send_response(self, call: CallRpc, response: RpcResponse) -> None:
        result = response.obj
        if isinstance(result, NeedsContextValues):
            result = result.obj
        if not isinstance(result, RpcResult):
            raise RuntimeError(f"Expected worker to return RpcResult object, got {result.__class__.__name__}")
        await self.nc.publish(
            NATS_WORKER_RPC_RESPONSE_SUBJECT.format(
                key_id=call.auth_key_id,
                session_id=call.session_id,
                req_msg_id=result.req_msg_id,
            ),
            response.write(),
        )

    @staticmethod
    def _err_response(req_msg_id: int, code: int, message: str) -> RpcResponse:
        return RpcResponse(obj=RpcResult(
            req_msg_id=req_msg_id,
            result=RpcError(error_code=code, error_message=message),
        ))

    @staticmethod
    def _err_response_internal(code: int, message: str) -> RpcError:
        return RpcError(error_code=code, error_message=message)

    async def _handle_tl_rpc(self, msg: NatsMsg) -> None:
        with measure_time("read CallRpc"):
            call = CallRpc.read(BytesIO(msg.data), True)

        logger.trace("Got request: {call!r}", call=call)

        req_message_id = cast(int, call.message_id)

        if not (handler := self.request_handlers.get(call.obj.tlid())) or handler.is_internal:
            logger.warning("No handler found for obj: {obj}", obj=call.obj)
            return await self._rpc_send_response(call, self._err_response(req_message_id, 500, "NOT_IMPLEMENTED"))
        if handler.is_internal:
            logger.warning("Client tried to execute internal request: {call!r}", call=call)
            return await self._rpc_send_response(call, self._err_response(req_message_id, 500, "NOT_IMPLEMENTED"))

        # TODO: send this error from gateway
        if call.is_bot and handler.bots_not_allowed:
            return await self._rpc_send_response(call, self._err_response(req_message_id, 400, "BOT_METHOD_INVALID"))
        elif not call.is_bot and handler.users_not_allowed:
            return await self._rpc_send_response(call, self._err_response(req_message_id, 400, "USER_BOT_REQUIRED"))

        user = None
        if (handler.auth_required or handler.has_user_arg) and not handler.dont_fetch_user:
            try:
                with measure_time(".get_user(...)"):
                    user = await self.get_user(call, handler.allow_mfa_pending, handler.prefetch_username)
            except ErrorRpc as e:
                return await self._rpc_send_response(
                    call, self._err_response(req_message_id, e.error_code, e.error_message),
                )

            if user is None and handler.auth_required:
                return await self._rpc_send_response(
                    call, self._err_response(req_message_id, 401, "AUTH_KEY_UNREGISTERED"),
                )
        elif handler.dont_fetch_user and handler.auth_required:
            if not call.user_id:
                return await self._rpc_send_response(
                    call, self._err_response(req_message_id, 401, "AUTH_KEY_UNREGISTERED"),
                )
            if call.mfa_pending and not handler.allow_mfa_pending:
                return await self._rpc_send_response(
                    call, self._err_response(req_message_id, 401, "SESSION_PASSWORD_NEEDED"),
                )

        ctx_token = request_ctx.set(RequestContext(
            cast(int, call.auth_key_id), call.perm_auth_key_id, req_message_id, cast(int, call.session_id), call.layer,
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
            req_msg_id=req_message_id,
            result=result,
        )

        if not isinstance(result_obj.result, RpcError):
            ctx = NeedContextValuesContext()
            result_obj.check_for_ctx_values(ctx)
            if ctx.any():
                result_obj = ctx.to_tl(result_obj)

        logger.trace("Returning to gateway: {result!r}", result=result_obj)

        return await self._rpc_send_response(call, RpcResponse(obj=result_obj, refresh_auth=handler.refresh_session))

    async def _handle_tl_rpc_internal(self, msg: NatsMsg) -> None:
        with measure_time("read CallRpc"):
            call = CallRpcInternal.read(BytesIO(msg.data), True)

        logger.trace("Got internal request: {call!r}", call=call)

        if not (handler := self.request_handlers.get(call.obj.tlid())):
            logger.warning("No handler found for obj: {obj}", obj=call.obj)
            return  # self._err_response_internal(500, "NOT_IMPLEMENTED")
        if not handler.is_internal:
            logger.warning("Tried to execute non-internal request: {call!r}", call=call)
            return  # self._err_response_internal(500, "ERROR_METHOD_NOT_INTERNAL")

        ctx_token = request_ctx.set(RequestContext(
            0, 0, 0, 0, layer, call.as_auth_id or 0, call.as_user or 0, self, self._storage,
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

        # if isinstance(self.broker.result_backend, InmemoryResultBackend):
        #     return result
        # else:
        #     return result.write().hex()
