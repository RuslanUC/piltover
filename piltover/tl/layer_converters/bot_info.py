from __future__ import annotations
from typing import TYPE_CHECKING
from piltover import tl
if TYPE_CHECKING:
    from piltover.tl.serialization_context import SerializationContext


def downgrade_user_id_for_133(obj: tl.types.BotInfo, _: SerializationContext) -> int:
    if obj.user_id is not None:
        return obj.user_id
    return 0


def downgrade_description_for_133(obj: tl.types.BotInfo, _: SerializationContext) -> str:
    if obj.description is not None:
        return obj.description
    return ""


def downgrade_commands_for_133(obj: tl.types.BotInfo, _: SerializationContext) -> list[tl.base.BotCommand]:
    if obj.commands is not None:
        return obj.commands
    return []


def downgrade_menu_button_for_140(obj: tl.types.BotInfo, _: SerializationContext) -> tl.base.BotMenuButton:
    if obj.menu_button is not None:
        return obj.menu_button
    return tl.types.BotMenuButtonDefault()
