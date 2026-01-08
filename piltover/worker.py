from __future__ import annotations

from collections import defaultdict
from inspect import getfullargspec
from io import BytesIO
from pathlib import Path
from typing import Awaitable, Callable, Any, TypeVar

from loguru import logger
from taskiq import InMemoryBroker, TaskiqEvents
from tortoise.transactions import in_transaction

from piltover._faster_taskiq_inmemory_result_backend import FasterInmemoryResultBackend
from piltover.db.enums import PeerType
from piltover.message_brokers.base_broker import BrokerType
from piltover.message_brokers.in_memory_broker import InMemoryMessageBroker
from piltover.message_brokers.rabbitmq_broker import RabbitMqMessageBroker
from piltover.pubsub.in_memory_pubsub import InMemoryPubSub
from piltover.session_manager import SessionManager
from piltover.storage import LocalFileStorage
from piltover.tl.functions.internal import CallRpc
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

from piltover.context import RequestContext, request_ctx
from piltover.db.models import UserAuthorization, User, Message
from piltover.enums import ReqHandlerFlags
from piltover.exceptions import ErrorRpc
from piltover.tl import TLObject, RpcError, TLRequest, layer
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

    def bots_not_allowed(self) -> bool:
        return bool(self.flags & ReqHandlerFlags.BOT_NOT_ALLOWED)

    def refresh_session(self) -> bool:
        return bool(self.flags & ReqHandlerFlags.REFRESH_SESSION)

    def users_not_allowed(self) -> bool:
        return bool(self.flags & ReqHandlerFlags.USER_NOT_ALLOWED)

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

    def on_request(
            self, typ: type[TLRequest[T]], flags: ReqHandlerFlags = 0,
    ) -> Callable[[HandlerFunc[T]], HandlerFunc[T]]:
        def decorator(func: HandlerFunc[T]):
            if typ.tlid() in self.request_handlers:
                logger.warning(f"Overriding existing handler for {typ.tlname()} ({hex(typ.tlid())[2:]})")

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

        # TODO: add RedisPubSub
        self.pubsub = InMemoryPubSub()

        # self.broker.register_task(self._handle_tl_rpc, "handle_tl_rpc")
        self.broker.register_task(self._handle_tl_rpc_measure_time, "handle_tl_rpc")
        self.broker.register_task(self._handle_scheduled_message, "send_scheduled")
        self.broker.register_task(self._handle_scheduled_delete_message, "delete_scheduled")
        self.broker.add_event_handler(TaskiqEvents.WORKER_STARTUP, self._broker_startup)
        self.broker.add_event_handler(TaskiqEvents.WORKER_SHUTDOWN, self._broker_shutdown)

    async def _broker_startup(self, _) -> None:
        await self.message_broker.startup()
        SessionManager.set_broker(self.message_broker)
        await self.pubsub.startup()

    async def _broker_shutdown(self, _) -> None:
        await self.message_broker.shutdown()
        await self.pubsub.startup()

    @classmethod
    async def get_user(cls, call: CallRpc, allow_mfa_pending: bool = False) -> User | None:
        if call.user_id is None or call.auth_id is None:
            return None

        auth = await UserAuthorization.get_or_none(user__id=call.user_id, id=call.auth_id).select_related("user")
        if auth is not None and not allow_mfa_pending and auth.mfa_pending:
            raise ErrorRpc(error_code=401, error_message="SESSION_PASSWORD_NEEDED")

        return auth.user if auth is not None else None

    async def _handle_tl_rpc_measure_time(self, call_hex: str) -> RpcResponse:
        with measure_time("_handle_tl_rpc()"):
            return await self._handle_tl_rpc(call_hex)

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

        # TODO: send this error from gateway
        if call.is_bot and handler.bots_not_allowed():
            return RpcResponse(obj=RpcResult(
                req_msg_id=call.message_id,
                result=RpcError(error_code=400, error_message="BOT_METHOD_INVALID"),
            ))
        elif not call.is_bot and handler.users_not_allowed():
            return RpcResponse(obj=RpcResult(
                req_msg_id=call.message_id,
                result=RpcError(error_code=400, error_message="USER_BOT_REQUIRED"),
            ))

        user = None
        if handler.auth_required() or handler.has_user_arg:
            try:
                user = await self.get_user(call, handler.allow_mfa_pending())
            except ErrorRpc as e:
                return RpcResponse(obj=RpcResult(
                    req_msg_id=call.message_id,
                    result=RpcError(error_code=e.error_code, error_message=e.error_message),
                ))

            if user is None and handler.auth_required():
                return RpcResponse(obj=RpcResult(
                    req_msg_id=call.message_id,
                    result=RpcError(error_code=401, error_message="AUTH_KEY_UNREGISTERED"),
                ))

        ctx_token = request_ctx.set(RequestContext(
            call.auth_key_id, call.perm_auth_key_id, call.message_id, call.session_id, call.obj, call.layer,
            call.auth_id, call.user_id, self, self._storage,
        ))

        try:
            with measure_time(f"handler({call.obj.tlname()})"):
                # TODO: wrap handler call in in_transaction?
                result = await handler(call.obj, user)
        except ErrorRpc as e:
            reason = f", reason: {e.reason}" if e.reason is not None else ""
            logger.warning(f"{call.obj.tlname()}: [{e.error_code} {e.error_message}]{reason}")
            result = RpcError(error_code=e.error_code, error_message=e.error_message)
        except Exception as e:
            logger.opt(exception=e).warning(f"Error while processing {call.obj.tlname()}")
            result = RpcError(error_code=500, error_message="Server error")

        request_ctx.reset(ctx_token)

        if result is None:
            logger.warning(f"Handler for {call.obj} returned None")
            result = RpcError(error_code=500, error_message="Not implemented")

        return RpcResponse(
            obj=RpcResult(
                req_msg_id=call.message_id,
                result=result,
            ),
            refresh_auth=handler.refresh_session(),
        )

    async def _handle_scheduled_message(self, message_id: int) -> None:
        from piltover.app.handlers.messages import sending
        import piltover.app.utils.updates_manager as upd

        logger.trace(f"Processing scheduled message {message_id}")

        async with in_transaction():
            scheduled = await Message.select_for_update(
                skip_locked=True, no_key=True,
            ).get_or_none(
                id=message_id,
            ).select_related(
                "taskiqscheduledmessages", "peer", "peer__owner", "peer__user", "author", "media", "reply_to",
                "fwd_header", "post_info",
            )
            if scheduled is None:
                logger.warning(f"Scheduled message {message_id} does not exist?")
                return

            task = scheduled.taskiqscheduledmessages
            peer = scheduled.peer

            ctx_token = request_ctx.set(RequestContext(
                1, 1, 0, 0, None, layer, -1, scheduled.peer.owner_id, self, self._storage,
            ))

            messages = await scheduled.send_scheduled(task.opposite)

            await sending.send_created_messages_internal(
                messages, task.opposite, scheduled.peer, scheduled.peer.owner, False, task.mentioned_users_set,
            )

            request_ctx.reset(ctx_token)

            await scheduled.delete()

        if peer.type is PeerType.CHANNEL and task.opposite:
            new_message = next(iter(messages.values()))
        else:
            new_message = messages[peer]

        await upd.delete_scheduled_messages(peer.owner, peer, [scheduled.id], [new_message.id])

    async def _handle_scheduled_delete_message(self, message_id: int) -> None:
        import piltover.app.utils.updates_manager as upd

        internal_id = await Message.filter(id=message_id).first().values_list("internal_id", flat=True)
        if internal_id is None:
            return

        async with in_transaction():
            to_delete = await Message.select_for_update(
                skip_locked=True, no_key=True,
            ).filter(internal_id=internal_id).select_related("peer", "peer__owner", "peer__channel")

            all_ids = []
            regular_messages = defaultdict(list)
            channel_messages = defaultdict(list)

            for message in to_delete:
                all_ids.append(message.id)
                if message.peer.type is PeerType.CHANNEL:
                    channel_messages[message.peer.channel_id].append(message.id)
                else:
                    regular_messages[message.peer.owner].append(message.id)

            await Message.filter(id__in=all_ids).delete()

            if regular_messages:
                await upd.delete_messages(None, regular_messages)
            for channel, message_ids in channel_messages.items():
                await upd.delete_messages_channel(channel, message_ids)
