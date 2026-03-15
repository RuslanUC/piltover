from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Callable, Awaitable, Generic, TypeVar, Optional, Self, Protocol

from piltover.db.models import Peer, MessageRef
from piltover.db.models.bot_state_base import BotUserStateBase, StateEnumT

StateT = TypeVar("StateT", bound=BotUserStateBase)
HandlerFunc = Callable[[Peer, MessageRef, StateT | None], Awaitable[MessageRef]]
EntityDict = dict[str, str | int]
Entities = list[EntityDict]


class SendMessageFunc(Protocol):
    async def __call__(self, peer: Peer, text: str, entities: Entities | None = None) -> MessageRef:
        ...


class HandlerBase(ABC, Generic[StateEnumT, StateT]):
    @abstractmethod
    async def __call__(self, peer: Peer, message: MessageRef, state: StateT | None) -> MessageRef | None:
        ...


class FuncHandler(HandlerBase):
    def __init__(self, func: HandlerFunc) -> None:
        self._func = func

    async def __call__(self, peer: Peer, message: MessageRef, state: StateT | None) -> MessageRef | None:
        return await self._func(peer, message, state)


class SimpleHandler(HandlerBase[StateEnumT, StateT]):
    def __init__(
            self,
            set_state: Optional[StateEnumT],
            text: str | None,
            entities: Entities | None,
            send_message: SendMessageFunc | None,
            del_state: bool,
    ) -> None:
        self._set_state: Optional[StateEnumT] = set_state
        self._respond_text = text
        self._respond_entities = entities
        self._send_message = send_message
        self._del_state = del_state

    async def __call__(self, peer: Peer, message: MessageRef, state: StateT | None) -> MessageRef | None:
        if self._set_state is not None:
            await state.update_state(self._set_state, None)
        if self._send_message is not None and self._respond_text is not None:
            return await self._send_message(peer, self._respond_text, entities=self._respond_entities)


class PendingHandler:
    def __init__(self) -> None:
        self.state: Optional[StateEnumT] = None
        self.func: HandlerFunc | None = None
        self.set_state: Optional[StateEnumT] = None
        self.del_state: bool = False
        self.respond_text: str | None = None
        self.respond_entities: Entities | None = None
        self.is_otherwise = False

    def clone(self) -> Self:
        pending = self.__class__.__new__(self.__class__)
        pending.state = self.state
        pending.func = self.func
        pending.set_state = self.set_state
        pending.del_state = self.del_state
        pending.respond_text = self.respond_text
        pending.respond_entities = self.respond_entities
        pending.is_otherwise = self.is_otherwise
        return pending


class RegisterInteraction(Generic[StateEnumT, StateT]):
    def __init__(self, int_handler: BotInteractionHandler) -> None:
        self._int_handler = int_handler
        self._handlers: dict[StateEnumT, HandlerBase[StateEnumT, StateT]] = {}
        self._need_fetch_state: bool = False
        self._otherwise: HandlerBase[StateEnumT, StateT] | None = None
        self._pending: PendingHandler = PendingHandler()
        self._send_message_func: SendMessageFunc | None = None

    @property
    def handlers(self) -> dict[StateEnumT, HandlerBase[StateEnumT, StateT]]:
        return self._handlers

    @property
    def otherwise_handler(self) -> HandlerBase[StateEnumT, StateT] | None:
        return self._otherwise

    @property
    def need_fetch_state(self) -> bool | None:
        return self._need_fetch_state

    def _clone(self) -> Self:
        reg = self.__class__.__new__(self.__class__)
        reg._int_handler = self._int_handler
        reg._handlers = self._handlers.copy()
        reg._need_fetch_state = self._need_fetch_state
        reg._otherwise = self._otherwise
        reg._pending = self._pending.clone()
        reg._send_message_func = self._send_message_func
        return reg

    def register(self) -> None:
        self._int_handler.register(self)

    def set_send_message_func(self, func: SendMessageFunc) -> Self:
        reg = self._clone()
        reg._send_message_func = func
        return reg

    def when(self, *, state: Optional[StateEnumT] = None) -> Self:
        reg = self._clone()
        reg._pending = PendingHandler()
        reg._pending.state = state
        return reg

    def fetch_state(self) -> Self:
        reg = self._clone()
        reg._fetch_state = True
        return reg

    def do(self, handler: HandlerFunc | None = None) -> Self:
        reg = self._clone()
        if handler is not None:
            reg._handlers[reg._pending.state] = FuncHandler(handler)
        else:
            reg._pending = PendingHandler()
            reg._pending.is_otherwise = False
        return reg

    def set_state(self, new_state: StateEnumT) -> Self:
        reg = self._clone()
        reg._pending.set_state = new_state
        return reg

    def delete_state(self) -> Self:
        reg = self._clone()
        reg._pending.del_state = True
        return reg

    def respond(self, text: str, entities: Entities | None = None) -> Self:
        if self._send_message_func is None:
            raise ValueError("Must call .set_send_message_func first")
        reg = self._clone()
        reg._pending.respond_text = text
        reg._pending.respond_entities = entities
        return reg

    def otherwise(self, handler: HandlerFunc | None = None) -> Self:
        reg = self._clone()
        if handler is not None:
            reg._otherwise = FuncHandler(handler)
        else:
            reg._pending = PendingHandler()
            reg._pending.is_otherwise = True
        return reg

    def ok(self) -> Self:
        reg = self._clone()
        if reg._pending.func is not None:
            if reg._pending.is_otherwise:
                reg._otherwise = FuncHandler(reg._pending.func)
            else:
                reg._handlers[reg._pending.state] = FuncHandler(reg._pending.func)
        elif reg._pending.respond_text is not None and self._send_message_func is not None:
            handler = SimpleHandler(
                set_state=reg._pending.set_state,
                text=reg._pending.respond_text,
                entities=reg._pending.respond_entities,
                send_message=reg._send_message_func,
                del_state=reg._pending.del_state,
            )
            if reg._pending.is_otherwise:
                reg._otherwise = handler
            else:
                reg._handlers[reg._pending.state] = handler

        return reg


class RegisterCommand(RegisterInteraction[StateEnumT, StateT]):
    def __init__(self, name: str, int_handler: BotInteractionHandler) -> None:
        super().__init__(int_handler)
        self._name = name

    @property
    def name(self) -> str:
        return self._name

    def _clone(self) -> Self:
        reg = super()._clone()
        reg._name = self._name
        return reg


class BotInteractionHandler(Generic[StateEnumT, StateT]):
    def __init__(self, state_cls: type[StateT] | None) -> None:
        self.state_cls = state_cls
        self._commands_registry: dict[tuple[str, Optional[StateEnumT]], HandlerBase[StateEnumT, StateT]] = {}
        self._command_fetch_state: dict[str, bool] = {}
        self._text_registry: dict[Optional[StateEnumT], HandlerBase[StateEnumT, StateT]] = {}

    def register(self, reg: RegisterInteraction[StateEnumT, StateT]) -> None:
        if isinstance(reg, RegisterCommand):
            for state, handler in reg.handlers.items():
                self._commands_registry[(reg.name, state)] = handler
            if reg.otherwise_handler is not None:
                self._commands_registry[reg.name, None] = reg.otherwise_handler
            self._command_fetch_state[reg.name] = reg.need_fetch_state or bool(reg.handlers)
        else:
            for state, handler in reg.handlers.items():
                self._text_registry[state] = handler
            if reg.otherwise_handler is not None:
                self._text_registry[None] = reg.otherwise_handler

    def include(self, other: BotInteractionHandler[StateEnumT, StateT]) -> None:
        if self.state_cls != other.state_cls:
            raise ValueError("Can't include interaction handler with different state class")
        self._commands_registry.update(other._commands_registry)
        self._command_fetch_state.update(other._command_fetch_state)
        self._text_registry.update(other._text_registry)

    def text(self) -> RegisterInteraction[StateEnumT, StateT]:
        return RegisterInteraction(self)

    def command(self, name: str) -> RegisterCommand[StateEnumT, StateT]:
        return RegisterCommand(name, self)

    async def handle_command(self, command: str, peer: Peer, message: MessageRef) -> MessageRef | None:
        state = None
        if self.state_cls is not None and self._command_fetch_state.get(command, False):
            state = await self.state_cls.get_or_none(user=peer.owner)

        if state is not None:
            key = command, state.state
            if key in self._commands_registry:
                return await self._commands_registry[key](peer, message, None)

        key = command, None
        if key in self._commands_registry:
            return await self._commands_registry[key](peer, message, None)

    async def handle_text(self, peer: Peer, message: MessageRef) -> MessageRef | None:
        state = None
        if self.state_cls is not None:
            state = await self.state_cls.get_or_none(user=peer.owner)

        state_step = state.state if state is not None else None
        if state_step in self._text_registry:
            return await self._text_registry[state_step](peer, message, state)
