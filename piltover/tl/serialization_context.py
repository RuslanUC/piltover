from __future__ import annotations

from typing import TYPE_CHECKING

from .layer_info import layer as tl_base_layer

if TYPE_CHECKING:
    from piltover.db.enums import PrivacyRuleKeyType
    from piltover.db.models import ChatParticipant, Contact
    from piltover.tl.base import MessageReactions


class ContextValues:
    __slots__ = (
        "poll_answers", "chat_participants", "channel_participants", "contacts", "privacyrules", "channel_messages",
    )

    def __init__(self) -> None:
        self.poll_answers: dict[int, set[int]] = {}
        self.chat_participants: dict[int, ChatParticipant] = {}
        self.channel_participants: dict[int, ChatParticipant] = {}
        self.contacts: dict[tuple[int, int], Contact] = {}
        self.privacyrules: dict[int, dict[PrivacyRuleKeyType, bool]] = {}
        self.channel_messages: dict[int, tuple[MessageReactions, bool, bool]] = {}

    def __repr__(self) -> str:
        fields = [f"{key}={getattr(self, key)!r}" for key in self.__slots__ if getattr(self, key)]
        return f"{self.__class__.__name__}({', '.join(fields)})"


_EMPTY_CONTEXT_VALUES = ContextValues()


class SerializationContext:
    __slots__ = ("auth_id", "user_id", "layer", "dont_format", "values",)

    def __init__(
            self, auth_id: int, user_id: int, layer: int, dont_format: bool = False,
            values: ContextValues | None = None,
    ):
        self.auth_id = auth_id
        self.user_id = user_id
        self.layer = layer
        self.dont_format = dont_format
        self.values = values or _EMPTY_CONTEXT_VALUES


EMPTY_SERIALIZATION_CONTEXT = SerializationContext(
    auth_id=0,
    user_id=0,
    layer=tl_base_layer,
    dont_format=True,
    values=None,
)
