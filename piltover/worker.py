from __future__ import annotations

from collections.abc import Callable, Awaitable
from inspect import getfullargspec
from io import BytesIO
from pathlib import Path
from typing import Any, TypeVar, cast, Protocol, ParamSpec

from loguru import logger
from nats import NATS
from nats.aio.msg import Msg

from piltover import context
from piltover.context import RequestContext, request_ctx, NeedContextValuesContext
from piltover.db.models import User
from piltover.enums import ReqHandlerFlags
from piltover.exceptions import ErrorRpc
from piltover.storage import LocalFileStorage
from piltover.tl import TLObject, RpcError, TLRequest
from piltover.tl.core_types import RpcResult
from piltover.tl.functions.internal import CallRpc, CallRpcInternal
from piltover.tl.layer_info import layer
from piltover.tl.types.internal import RpcResponse, ObjectWithLayerRequirement, MessageToClient, SetInternalPush, \
    NotifyInternalPush, ChannelSubscribe, ChannelUnsubscribe
from piltover.utils import get_public_key_fingerprint
from piltover.utils.debug import measure_time

T = TypeVar("T", covariant=True)
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

        if not isinstance(self, Worker) or not self._testing:
            if clear:
                handler.request_handlers.clear()
            handler.registered = True


class Worker(MessageHandler):
    def __init__(self, data_dir: Path, public_key: str, nats: NATS, *, _testing: bool = False) -> None:
        super().__init__()

        self._storage = LocalFileStorage(data_dir)
        self.public_key = public_key
        self.fingerprint: int = get_public_key_fingerprint(self.public_key)

        self.nats = nats
        self._testing = _testing

    async def startup(self) -> None:
        await self.nats.subscribe("piltover.worker.rpc.public", queue="workers", cb=self._handle_tl_rpc)
        await self.nats.subscribe("piltover.worker.rpc.internal", queue="workers", cb=self._handle_tl_rpc_internal)

    async def call_internal(self, request: TLObject) -> None:
        await self.nats.publish("piltover.worker.rpc.internal", CallRpcInternal(obj=request).write())

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

    async def _handle_tl_rpc_measure_time(self, message: Msg) -> None:
        with measure_time("_handle_tl_rpc()"):
            return await self._handle_tl_rpc(message)

    @staticmethod
    async def _reply_err(request: Msg, req_msg_id: int, code: int, message: str) -> None:
        response = RpcResponse(
            obj=RpcResult(
                req_msg_id=req_msg_id,
                result=RpcError(error_code=code, error_message=message),
            )
        )

        await request.respond(response.write())

    @staticmethod
    async def _err_response_internal(request: Msg, code: int, message: str) -> None:
        response = RpcError(error_code=code, error_message=message)
        if request.reply:
            await request.respond(response.write())

    async def _handle_tl_rpc(self, message: Msg) -> None:
        with measure_time("read CallRpc"):
            call = CallRpc.read(BytesIO(message.data), True)

        logger.trace("Got request: {call!r}", call=call)

        req_message_id = cast(int, call.message_id)

        if (handler := self.request_handlers.get(call.obj.tlid())) is None:
            logger.warning("No handler found for obj: {obj}", obj=call.obj)
            return await self._reply_err(message, req_message_id, 500, "NOT_IMPLEMENTED")
        if handler.is_internal:
            logger.warning("Client tried to execute internal request: {call!r}", call=call)
            return await self._reply_err(message, req_message_id, 500, "NOT_IMPLEMENTED")

        # TODO: send this error from gateway
        if call.is_bot and handler.bots_not_allowed:
            return await self._reply_err(message, req_message_id, 400, "BOT_METHOD_INVALID")
        elif not call.is_bot and handler.users_not_allowed:
            return await self._reply_err(message, req_message_id, 400, "USER_BOT_REQUIRED")

        user = None
        if (handler.auth_required or handler.has_user_arg) and not handler.dont_fetch_user:
            try:
                with measure_time(".get_user(...)"):
                    user = await self.get_user(call, handler.allow_mfa_pending, handler.prefetch_username)
            except ErrorRpc as e:
                return await self._reply_err(message, req_message_id, e.error_code, e.error_message)

            if user is None and handler.auth_required:
                return await self._reply_err(message, req_message_id, 401, "AUTH_KEY_UNREGISTERED")
        elif handler.dont_fetch_user and handler.auth_required:
            if not call.user_id:
                return await self._reply_err(message, req_message_id, 401, "AUTH_KEY_UNREGISTERED")
            if call.mfa_pending and not handler.allow_mfa_pending:
                return await self._reply_err(message, req_message_id, 401, "SESSION_PASSWORD_NEEDED")

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
        except Exception as e:  # noqa: BLE001
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

        response = RpcResponse(
            obj=result_obj,
            refresh_auth=handler.refresh_session,
        )

        return await message.respond(response.write())

    async def _handle_tl_rpc_internal(self, message: Msg) -> None:
        with measure_time("read CallRpc"):
            call = CallRpcInternal.read(BytesIO(message.data), True)

        logger.trace("Got internal request: {call!r}", call=call)

        if not (handler := self.request_handlers.get(call.obj.tlid())):
            logger.warning("No handler found for obj: {obj}", obj=call.obj)
            return await self._err_response_internal(message, 500, "NOT_IMPLEMENTED")
        if not handler.is_internal:
            logger.warning("Tried to execute non-internal request: {call!r}", call=call)
            return await self._err_response_internal(message, 500, "ERROR_METHOD_NOT_INTERNAL")

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
        except Exception as e:  # noqa: BLE001
            logger.opt(exception=e).warning(f"Error while processing {call.obj.tlname()}")
            result = RpcError(error_code=500, error_message="Server error")
        finally:
            request_ctx.reset(ctx_token)

        if result is None:
            logger.warning(f"Handler for {call.obj} returned None")
            result = RpcError(error_code=500, error_message="NOT_IMPLEMENTED")

        logger.trace("Returning internal result: {result!r}", result=result)

        if message.reply:
            await message.respond(result.write())

    async def send_message_to_client(
            self, obj: TLObject, user_id: int | list[int] | None = None, key_id: int | list[int] | None = None,
            channel_id: int | list[int] | None = None, auth_id: int | list[int] | None = None,
            ignore_session_id: int | None = None,
    ) -> None:
        if not user_id and not key_id and not channel_id and not auth_id:
            return

        user_ids = []
        if isinstance(user_id, list):
            user_ids = user_id
        elif user_id is not None:
            user_ids.append(user_id)

        key_ids = []
        if isinstance(key_id, list):
            key_ids = key_id
        elif key_id is not None:
            key_ids.append(key_id)

        channel_ids = []
        if isinstance(channel_id, list):
            channel_ids = channel_id
        elif channel_id is not None:
            channel_ids.append(channel_id)

        auth_ids = []
        if isinstance(auth_id, list):
            auth_ids = auth_id
        elif auth_id is not None:
            auth_ids.append(auth_id)

        ctx = NeedContextValuesContext()
        if isinstance(obj, TLObject):
            obj.check_for_ctx_values(ctx)

        if ctx.any():
            if isinstance(obj, ObjectWithLayerRequirement):
                obj.object = ctx.to_tl(obj.object)
                # TODO: this is (probably) a temporary fix (?)
                #  note: probably can move the whole "layer requirement" thing into "*ToFormat"?
                for field_ in obj.fields:
                    field_.field = f"obj.{field_.field}"
            else:
                obj = ctx.to_tl(cast(TLObject, obj))

        to_send = MessageToClient(ignore_session_id=ignore_session_id, obj=obj).write()

        for publish_user_id in user_ids:
            await self.nats.publish(f"piltover.client.user.{publish_user_id}", to_send)
        for publish_key_id in key_ids:
            await self.nats.publish(f"piltover.client.key.{publish_key_id}", to_send)
        for publish_channel_id in channel_ids:
            await self.nats.publish(f"piltover.client.channel-sub.{publish_channel_id}", to_send)
        for publish_auth_id in auth_ids:
            await self.nats.publish(f"piltover.client.auth.{publish_auth_id}", to_send)

    async def subscribe_to_internal_push(self, key_id: int, session_id: int) -> None:
        await self.nats.publish(f"piltover.client.session.{key_id}-{session_id}", SetInternalPush().write())

    async def send_internal_push(self, user_id: int | list[int]) -> None:
        if not user_id:
            return

        if isinstance(user_id, list):
            user_ids = user_id
        else:
            user_ids = [user_id]

        to_send = NotifyInternalPush().write()

        for publish_user_id in user_ids:
            await self.nats.publish(f"piltover.client.internal-push.{publish_user_id}", to_send)

    async def subscribe_to_channel(self, channel_id: int, user_ids: list[int]) -> None:
        to_send = ChannelSubscribe(channel_id=channel_id).write()
        for user_id in user_ids:
            await self.nats.publish(f"piltover.client.user.{user_id}", to_send)

    async def unsubscribe_from_channel(self, channel_id: int, user_ids: list[int]) -> None:
        to_send = ChannelUnsubscribe(channel_id=channel_id).write()
        for user_id in user_ids:
            await self.nats.publish(f"piltover.client.user.{user_id}", to_send)
