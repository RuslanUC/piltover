from __future__ import annotations

from asyncio import StreamReader, StreamWriter
from inspect import getfullargspec
from typing import Awaitable, Callable, Any

from loguru import logger

from piltover.context import request_ctx
from piltover.db.models import UserAuthorization, User
from piltover.enums import ReqHandlerFlags
from piltover.exceptions import ErrorRpc
from piltover.server import Server as LowServer, Client as LowClient, MessageHandler as LowMessageHandler
from piltover.session_manager import Session, SessionManager
from piltover.tl import TLObject, RpcError, Ping, Pong
from piltover.tl.core_types import MsgContainer, RpcResult, Message
from piltover.utils import background
from piltover.utils.utils import check_flag

HandlerResult = Awaitable[TLObject | None]
HandlerFunc = (Callable[[], HandlerResult] |
               Callable[[LowClient], HandlerResult] |
               Callable[[TLObject], HandlerResult] |
               Callable[[User], HandlerResult] |
               Callable[[LowClient, TLObject], HandlerResult] |
               Callable[[LowClient, User], HandlerResult] |
               Callable[[TLObject, User], HandlerResult] |
               Callable[[LowClient, TLObject, User], HandlerResult])


class RequestHandler:
    __slots__ = ("func", "flags", "has_client_arg", "has_request_arg", "has_user_arg",)

    def __init__(self, func: HandlerFunc, flags: int):
        self.func = func
        self.flags = flags
        func_args = set(getfullargspec(func).args)
        self.has_client_arg = "client" in func_args
        self.has_request_arg = "request" in func_args
        self.has_user_arg = "user" in func_args

    def auth_required(self) -> bool:
        return check_flag(self.flags, ReqHandlerFlags.AUTH_REQUIRED)

    def allow_mfa_pending(self) -> bool:
        return check_flag(self.flags, ReqHandlerFlags.ALLOW_MFA_PENDING)

    async def __call__(self, client: LowClient, request: TLObject, user: User | None) -> Any:
        kwargs = {}
        if self.has_client_arg: kwargs["client"] = client
        if self.has_request_arg: kwargs["request"] = request
        if self.has_user_arg: kwargs["user"] = user

        return await self.func(**kwargs)


class MessageHandler:
    def __init__(self, name: str = None):
        self.name = name
        self.registered = False
        self.request_handlers: dict[int, RequestHandler] = {}

    def on_request(self, typ: type[TLObject], flags: int = 0):
        def decorator(func: HandlerFunc):
            logger.debug(f"Added handler for function {typ.tlname()}" + (f" on {self.name}" if self.name else ""))

            self.request_handlers[typ.tlid()] = RequestHandler(func, flags)
            return func

        return decorator

    def register_handler(self, handler: MessageHandler, clear: bool=True) -> None:
        if handler.registered:
            raise RuntimeError(f"Handler {handler} already registered!")

        self.request_handlers.update(handler.request_handlers)
        if clear:
            handler.request_handlers.clear()

        handler.registered = True


class Server(LowServer, MessageHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        super(LowServer, self).__init__(name="Server")

    async def accept_client(self, reader: StreamReader, writer: StreamWriter) -> None:
        client = Client(server=self, reader=reader, writer=writer)
        background(client.worker())

    def register_handler(self, handler: MessageHandler) -> None:
        return super(LowServer, self).register_handler(handler)

    def register_handler_low(self, handler: LowMessageHandler) -> None:
        return super().register_handler(handler)


class Client(LowClient):
    server: Server

    async def get_auth(self, allow_mfa_pending: bool = False) -> UserAuthorization | None:
        auth = await UserAuthorization.get_or_none(
            key__id=str(await self.auth_data.get_perm_id()),
        ).select_related("user")
        if auth is not None and not allow_mfa_pending and auth.mfa_pending:
            raise ErrorRpc(error_code=401, error_message="SESSION_PASSWORD_NEEDED")
        return auth

    async def get_user(self, allow_mfa_pending: bool=False) -> User | None:
        auth = await self.get_auth(allow_mfa_pending)
        return auth.user if auth is not None else None

    async def propagate(self, request: Message, session: Session) -> list[tuple[TLObject, Message]] | TLObject | None:
        if isinstance(request.obj, MsgContainer):
            return await super().propagate(request, session)

        if not (handler := self.server.request_handlers.get(request.obj.tlid())):
            return await super().propagate(request, session)

        old_ctx = request_ctx.get()
        request_ctx.set(old_ctx.clone(obj=request.obj))

        result = None
        error = None
        user = None

        try:
            if handler.auth_required() and (user := await self.get_user(handler.allow_mfa_pending())) is None:
                raise ErrorRpc(error_code=401, error_message="AUTH_KEY_UNREGISTERED")
            user = user if handler.auth_required() and handler.has_user_arg else None
            result = await handler(self, request.obj, user)
        except Exception as e:
            if isinstance(e, ErrorRpc):
                logger.warning(f"{request.obj.tlname()}: [{e.error_code} {e.error_message}]")
                error = RpcError(error_code=e.error_code, error_message=e.error_message)
            else:
                logger.opt(exception=e).warning(f"Error while processing {request.obj.tlname()}")
                error = RpcError(error_code=500, error_message="Server error")

        request_ctx.set(old_ctx)

        if user is not None and session.user_id is None:
            SessionManager().set_user(session, user)

        result = result if error is None else error
        if result is None:
            logger.warning(f"Handler for {request.obj} returned None")
            result = RpcError(error_code=500, error_message="Not implemented")

        if not isinstance(result, (Ping, Pong, RpcResult)):
            result = RpcResult(req_msg_id=request.message_id, result=result)

        return result
