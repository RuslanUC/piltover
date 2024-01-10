from __future__ import annotations

from collections import defaultdict
from inspect import signature
from typing import Awaitable, Callable

from loguru import logger

from piltover.db.models import UserAuthorization, User
from piltover.enums import Transport
from piltover.exceptions import ErrorRpc
from piltover.server import Server as LowServer, Client as LowClient, MessageHandler as LowMessageHandler
from piltover.tl.types import CoreMessage
from piltover.tl_new import TLObject, RpcError, Ping, Pong
from piltover.tl_new.primitives.types_ import MsgContainer, RpcResult
from piltover.utils import background
from piltover.utils.buffered_stream import BufferedStream

HandlerFunc = (Callable[["Client", TLObject], Awaitable[TLObject | dict | None]] |
               Callable[["Client", TLObject, User], Awaitable[TLObject | dict | None]])


class RequestHandler:
    __slots__ = ("func", "auth_required", "has_user_arg")

    def __init__(self, func: HandlerFunc, auth_required: bool, has_user_arg: bool):
        self.func = func
        self.auth_required = auth_required
        self.has_user_arg = has_user_arg


class MessageHandler:
    def __init__(self, name: str = None):
        self.name = name
        self.registered = False
        self.request_handlers: defaultdict[int, set[RequestHandler]] = defaultdict(set)

    def on_request(self, typ: type[TLObject], auth_required: bool=False):
        def decorator(func: HandlerFunc):
            logger.debug("Added handler for function {typ!r}" + (f" on {self.name}" if self.name else ""),
                         typ=typ.tlname())

            has_user_arg = auth_required and "user" in signature(func).parameters
            self.request_handlers[typ.tlid()].add(RequestHandler(func, auth_required, has_user_arg))
            return func

        return decorator

    def register_handler(self, handler: MessageHandler, clear: bool=True) -> None:
        if handler.registered:
            raise RuntimeError(f"Handler {handler} already registered!")
        for tlid, handlers in handler.request_handlers.items():
            self.request_handlers[tlid].update(handlers)

        if clear:
            handler.request_handlers.clear()

        handler.registered = True


class Server(LowServer, MessageHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        super(LowServer, self).__init__(name="Server")

    async def welcome(self, stream: BufferedStream, transport: Transport):
        client = Client(
            transport=transport,
            server=self,
            stream=stream,
            peername=stream.get_extra_info("peername"),
        )
        background(client.worker())

    def register_handler(self, handler: MessageHandler) -> None:
        return super(LowServer, self).register_handler(handler)

    def register_handler_low(self, handler: LowMessageHandler) -> None:
        return super().register_handler(handler)


class Client(LowClient):
    server: Server

    async def get_user(self) -> User | None:
        auth = await UserAuthorization.get_or_none(key__id=str(self.auth_data.auth_key_id)).select_related("user")
        return auth.user

    async def propagate(self, request: CoreMessage, session_id: int) -> None | list[tuple[TLObject, CoreMessage]] | TLObject:
        if isinstance(request.obj, MsgContainer):
            return await super().propagate(request, session_id)
        else:
            if not (handlers := self.server.request_handlers.get(request.obj.tlid(), [])):
                return await super().propagate(request, session_id)

            result = None
            error = None
            user = None
            for handler in handlers:
                try:
                    if handler.auth_required and (user := await self.get_user()) is None:
                        raise ErrorRpc(error_code=401, error_message="AUTH_KEY_UNREGISTERED")
                    user_arg = (user,) if handler.auth_required and handler.has_user_arg else ()
                    result = await handler.func(self, request.obj, *user_arg)
                    if result is not None:
                        break
                except Exception as e:
                    logger.warning("Error while processing {obj}: {err}", obj=request.obj.tlname(), err=e)
                    if error is not None:
                        continue

                    if isinstance(e, ErrorRpc):
                        error = RpcError(error_code=e.error_code, error_message=e.error_message)
                    else:
                        error = RpcError(error_code=500, error_message="Server error")

            result = result if error is None else error
            if result is None:
                logger.warning("No handler found for obj:\n{obj}", obj=request.obj)
                result = RpcError(error_code=500, error_message="Not implemented")
            #if result is False:
            #    return

            if not isinstance(result, (Ping, Pong, RpcResult)):
                result = RpcResult(req_msg_id=request.message_id, result=result)

            return result
